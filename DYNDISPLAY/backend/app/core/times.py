from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def get_app_tz() -> tzinfo:
    """Fuseau horaire de l'application.

    Priorité à la variable d'environnement APP_TIMEZONE (ex. Africa/Casablanca,
    Europe/Paris). À défaut, le fuseau du système (heure locale du serveur).
    """
    tz_name = get_settings().APP_TIMEZONE
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo


def now_app() -> datetime:
    """Date/heure courante dans le fuseau de l'application."""
    return datetime.now(get_app_tz())


def to_utc(dt: datetime) -> datetime:
    """Normalise un datetime vers UTC.

    Un datetime sans fuseau (naïve datetime) est interprété comme étant dans
    le fuseau de l'application, puis converti en UTC avant stockage.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_app_tz())
    return dt.astimezone(timezone.utc)