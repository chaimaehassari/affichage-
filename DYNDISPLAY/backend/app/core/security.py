import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from app.core.config import get_settings
from app.core.times import now_app

settings = get_settings()

ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        ph.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Décode un token de SESSION uniquement (typ=access).

    Les tokens média (typ=media) ne doivent JAMAIS être acceptés comme token
    d'API : ils circulent dans des URL et sont de simples accès signés à un
    fichier. La vérification stricte de `typ` empêche un token média volé
    d'être réutilisé comme session.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "access":
        return None
    return payload


def create_media_token(user_id: int, media_path: str) -> str:
    """Token dédié à l'accès d'UN SEUL fichier média via /media/{path}.

    Distinct du token de session : durée de vie courte (MEDIA_TOKEN_EXPIRE_MINUTES),
    scopé au chemin exact du média, typ=media. Porté dans l'URL (?token=) pour les
    balises <img>/<video>, donc volontairement inutilisable sur l'API.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.MEDIA_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "typ": "media",
        "media_path": media_path,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_media_token(token: str) -> dict | None:
    """Décode un token MÉDIA uniquement (typ=media, media_path présent)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "media":
        return None
    if not payload.get("media_path"):
        return None
    return payload


def verify_supreme_admin_code(code: str, username: str | None = None) -> bool:
    """Vérifie le code d'accès Admin suprême.

    Le code attendu est la date du jour au format JJMMAAAA (fuseau de
    l'application, ex. 17092026 pour le 17/09/2026) suivie du suffixe fixe
    SUPREME_ADMIN_SECRET (ex. 17092026X7K9). Le suffixe secret rend le code
    non devinable à partir de la seule connaissance de la date du jour.
    Comparaison à temps constant via secrets.compare_digest.
    """
    # Le nom d'utilisateur (login) n'est jamais un code valide.
    if username and code.strip().lower() == username.strip().lower():
        return False
    stripped = code.strip()

    # Date du jour au format JJMMAAAA dans le fuseau de l'application
    # (heure locale du serveur, ou fuseau configuré via APP_TIMEZONE).
    expected_code = now_app().strftime("%d%m%Y") + settings.SUPREME_ADMIN_SECRET
    return secrets.compare_digest(stripped, expected_code)
