from __future__ import annotations

import base64
import hmac
import hashlib
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

SIGNATURE_BYTES = 8
BLOCK_SIZE = 5
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

# Alphabet des codes d'activation de compte : sans 0/O/1/I pour éviter
# toute confusion à la saisie manuelle.
ACCOUNT_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Magic bytes du code d'activation de compte (HMAC signé, base32).
ACTIVATION_MAGIC = b"ACTV"
ACTIVATION_EXPIRY_DAYS = 7


def _b32_encode_nopad(data: bytes) -> str:
    """Base32 encode (RFC 4648) without padding — must match the Kotlin app."""
    encoded = base64.b32encode(data).decode("ascii").rstrip("=")
    return encoded


def _b32_decode_nopad(text: str) -> bytes:
    """Base32 decode (RFC 4648) without padding — must match the Kotlin app."""
    cleaned = "".join(c for c in text.upper() if c in _ALPHABET)
    padding = (-len(cleaned) % 8)
    cleaned += "=" * padding
    return base64.b32decode(cleaned)


def _sign(payload_bytes: bytes) -> bytes:
    """HMAC-SHA256 using LICENSE_SECRET, truncated to first 8 bytes."""
    settings = get_settings()
    if not settings.LICENSE_SECRET:
        raise RuntimeError(
            "LICENSE_SECRET est vide : le définir dans backend/.env "
            "(même valeur que local.properties → license.secret de l'app Android)."
        )
    mac = hmac.new(
        settings.LICENSE_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    )
    return mac.digest()[:SIGNATURE_BYTES]


@dataclass
class LicenseInfo:
    client_code: str
    sites: int
    posts: int


def validate_license(code: str) -> LicenseInfo | None:
    """Validate a license code and return decoded info, or None if invalid.

    Algorithm (must be bit-identical to the Android app and Python reference tool):
        payload   = "CODE_CLIENT:SITES:POSTES" (UTF-8)
        signature = HMAC-SHA256(LICENSE_SECRET, payload) -> first 8 bytes
        combined  = payload_bytes + signature_bytes
        code      = Base32(combined) (RFC 4648, no padding), formatted in
                    5-char blocks separated by dashes
    """
    cleaned = code.replace("-", "").strip()
    if not cleaned:
        return None

    try:
        combined = _b32_decode_nopad(cleaned)
    except Exception:
        return None

    if len(combined) < SIGNATURE_BYTES:
        return None

    payload_bytes = combined[:-SIGNATURE_BYTES]
    received_signature = combined[-SIGNATURE_BYTES:]
    expected_signature = _sign(payload_bytes)

    if not hmac.compare_digest(expected_signature, received_signature):
        return None

    payload = payload_bytes.decode("utf-8", errors="replace")
    parts = payload.split(":")
    if len(parts) != 3:
        return None

    try:
        sites = int(parts[1])
        posts = int(parts[2])
    except (ValueError, IndexError):
        return None

    if not parts[0] or sites < 0 or posts < 0:
        return None

    return LicenseInfo(client_code=parts[0], sites=sites, posts=posts)


def generate_license(client_code: str, sites: int, posts: int) -> str:
    """Generate a license code — identical algorithm to the Android app."""
    payload = f"{client_code}:{sites}:{posts}"
    payload_bytes = payload.encode("utf-8")
    signature = _sign(payload_bytes)
    combined = payload_bytes + signature
    encoded = _b32_encode_nopad(combined)
    return "-".join(encoded[i:i + BLOCK_SIZE] for i in range(0, len(encoded), BLOCK_SIZE))


# --- Codes d'activation des comptes (par appareil) ---


def generate_account_code(length: int = 8) -> str:
    """Génère un code d'activation de compte aléatoire (base32 lisible).

    Saisie manuelle sûre : pas de 0/O/1/I. Généré une seule fois à la
    création du compte (POST /users) et stocké sur le compte.
    """
    if length < 4:
        length = 4
    return "".join(secrets.choice(ACCOUNT_CODE_ALPHABET) for _ in range(length))


def fp6_from_string(value: str) -> bytes:
    """Empreinte 6 octets (SHA-256 tronqué) d'une chaîne — sert à identifier
    un compte dans un code d'activation sans exposer le code lui-même."""
    return hashlib.sha256(value.encode("utf-8")).digest()[:6]


def _epoch_days(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() // 86400)


def generate_activation_code(account_code: str, expires_at: datetime | None = None) -> str:
    """Génère un code d'activation de compte signé HMAC-SHA256.

    Payload : b"ACTV" + fp6(account_code) + epoch_days(expiration)
    le tout signé (_sign) et encodé en base32 sans padding (blocs de 5).
    """
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=ACTIVATION_EXPIRY_DAYS)
    payload = (
        ACTIVATION_MAGIC
        + fp6_from_string(account_code)
        + struct.pack(">I", _epoch_days(expires_at))
    )
    signature = _sign(payload)
    combined = payload + signature
    encoded = _b32_encode_nopad(combined)
    return "-".join(encoded[i:i + BLOCK_SIZE] for i in range(0, len(encoded), BLOCK_SIZE))


@dataclass
class ActivationInfo:
    account_fp6: bytes
    expires_at: datetime
    valid: bool


def verify_activation_code(activation_code: str, expected_fp6: bytes) -> ActivationInfo | None:
    """Vérifie un code d'activation et son adéquation avec l'empreinte d'un compte.

    Retourne None si le code est malformé / signature invalide.
    Retourne ActivationInfo(valid=False) si le code est valide mais pour un autre compte.
    Retourne ActivationInfo(valid=True) si le code correspond au compte attendu.
    """
    cleaned = activation_code.replace("-", "").strip().upper()
    if not cleaned:
        return None

    try:
        combined = _b32_decode_nopad(cleaned)
    except Exception:
        return None

    fixed_len = len(ACTIVATION_MAGIC) + 6 + 4 + SIGNATURE_BYTES
    if len(combined) != fixed_len:
        return None

    payload_bytes = combined[:-SIGNATURE_BYTES]
    received_signature = combined[-SIGNATURE_BYTES:]
    expected_signature = _sign(payload_bytes)
    if not hmac.compare_digest(expected_signature, received_signature):
        return None

    if not payload_bytes.startswith(ACTIVATION_MAGIC):
        return None

    fp6 = payload_bytes[len(ACTIVATION_MAGIC):len(ACTIVATION_MAGIC) + 6]
    days = struct.unpack(">I", payload_bytes[len(ACTIVATION_MAGIC) + 6:])[0]
    expires_at = datetime.fromtimestamp(days * 86400, tz=timezone.utc)

    return ActivationInfo(
        account_fp6=fp6,
        expires_at=expires_at,
        valid=hmac.compare_digest(fp6, expected_fp6 or b""),
    )
