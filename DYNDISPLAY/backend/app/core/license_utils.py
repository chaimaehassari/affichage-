from __future__ import annotations

import base64
import hmac
import hashlib
from dataclasses import dataclass

from app.core.config import get_settings

SIGNATURE_BYTES = 8
BLOCK_SIZE = 5
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


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
