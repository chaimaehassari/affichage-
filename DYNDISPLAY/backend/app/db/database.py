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
    kwargs={"row_factory": dict_row},
    min_size=1,
    max_size=10,
    open=False,
)


def init_db() -> None:
    if pool.closed:
        pool.open()


def close_db() -> None:
    if not pool.closed:
        pool.close()


def get_connection() -> Connection:
    if pool.closed:
        pool.open()
    return pool.connection(timeout=30)


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