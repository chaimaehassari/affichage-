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
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


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
