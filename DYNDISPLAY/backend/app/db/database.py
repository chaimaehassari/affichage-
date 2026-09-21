import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


def _build_url() -> str:
    if settings.DATABASE_URL:
        return _normalize_url(settings.DATABASE_URL)
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def connect_new() -> Connection:
    """Open a dedicated connection (outside the pool), used by background threads."""
    conn = psycopg.connect(_build_url())
    conn.row_factory = dict_row
    return conn


pool = ConnectionPool(
    conninfo=_build_url(),
    kwargs={"row_factory": dict_row, "application_name": "gesto-api"},
    min_size=1,
    max_size=10,
    open=False,
)

# Pool dédié aux threads de synchro : chaque worker du sync-executor prend
# sa connexion ICI (jamais une connexion brute hors pool). Sa taille est
# égale à SYNC_MAX_WORKERS : le nombre de connexions DB simultanées de la
# sync est donc borné de bout en bout (threads ET connexions), et l'API web
# (pool « gesto-api ») n'est jamais privée de ses connexions par l'orage
# d'auto-sync. application_name = "gesto-sync" permet de suivre la conso
# réelle dans pg_stat_activity.
_sync_max_workers = max(int(settings.SYNC_MAX_WORKERS or 8), 1)
sync_pool = ConnectionPool(
    conninfo=_build_url(),
    kwargs={"row_factory": dict_row, "application_name": "gesto-sync"},
    min_size=0,
    max_size=_sync_max_workers,
    open=False,
)


def init_db() -> None:
    if pool.closed:
        pool.open()
    if sync_pool.closed:
        sync_pool.open()


def close_db() -> None:
    if not sync_pool.closed:
        sync_pool.close()
    if not pool.closed:
        pool.close()


def get_connection() -> Connection:
    if pool.closed:
        pool.open()
    return pool.connection(timeout=30)


def get_sync_connection() -> Connection:
    """Connexion issue du pool sync (borné), pour les workers de synchro."""
    if sync_pool.closed:
        sync_pool.open()
    return sync_pool.connection(timeout=60)


def get_db():
    with pool.connection(timeout=30) as conn:
        try:
            yield conn
            conn.commit()
        except HTTPException:
            conn.commit()
            raise
        except Exception:
            conn.rollback()
            raise