import uuid
import psycopg
import pytest
import requests

from tests._test_config import get_test_db_url, get_test_admin_password

BASE_URL = "http://localhost:8000"
DB_URL = get_test_db_url()
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = get_test_admin_password()
TEST_DEVICE = "pytest-device-0001"


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

def login_as(
    login_str: str,
    password_str: str,
    client_code: str | None = None,
    device_id: str | None = TEST_DEVICE,
) -> str | None:
    body = {"login": login_str, "password": password_str}
    if client_code:
        body["client_code"] = client_code
    headers = {}
    if device_id:
        headers["X-Device-Id"] = device_id
    resp = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json=body,
        headers=headers,
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


def make_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Device-Id": TEST_DEVICE}


def generate_activation_code_for(account_code: str) -> str:
    from app.core.license_utils import generate_activation_code

    return generate_activation_code(account_code)


def activate_device_account(
    login: str,
    account_code: str,
    device_id: str = TEST_DEVICE,
) -> requests.Response:
    """Active un compte par appareil (équivalent de l'application mobile).

    Génère le code d'activation (même secret HMAC que le backend) puis
    l'échange contre POST /auth/activate-account.
    """
    code = generate_activation_code_for(account_code)
    return requests.post(
        f"{BASE_URL}/api/v1/auth/activate-account",
        json={"login": login, "activation_code": code},
        headers={"X-Device-Id": device_id},
    )


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