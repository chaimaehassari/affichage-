import uuid
import psycopg
import pytest
import requests

BASE_URL = "http://localhost:8000"
DB_URL = "postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY"
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin123"


# ---------------------------------------------------------------------------
# Auto-unlock admin before the session starts
# ---------------------------------------------------------------------------

def _unlock_admin():
    """Reset failed_attempts and locked_until for the admin user."""
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE login = %s",
                (ADMIN_LOGIN,),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login_as(login_str: str, password_str: str) -> str | None:
    resp = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"login": login_str, "password": password_str},
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


def make_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _ensure_admin_unlocked():
    """Automatically unlock admin account before any test runs."""
    _unlock_admin()


@pytest.fixture(scope="session")
def admin_token() -> str:
    """Log in as admin/admin123 and return the JWT token."""
    _unlock_admin()
    token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
    assert token is not None, "Failed to obtain admin token – is the API running?"
    return token


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict:
    return make_headers(admin_token)