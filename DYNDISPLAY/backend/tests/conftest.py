import uuid
import psycopg
import pytest
import requests

from tests._test_config import (
    assert_test_db_url,
    get_base_url,
    get_test_admin_password,
    get_test_db_url,
)

# Garde-fou : la base de tests doit contenir "_test". Si ce controle echoue,
# pytest s'arrete ici, AVANT la collecte et l'execution du moindre test, plutot
# que d'ecrire dans la base de production.
DB_URL = get_test_db_url()
assert_test_db_url(DB_URL)

BASE_URL = get_base_url()
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


# Nom public : les tests qui se connectent en direct (sans passer par le
# fixture `admin_token`) doivent déverrouiller le compte. Les tests de mot de
# passe faux des autres fichiers laissent le compte admin verrouillé, et un
# verrouillage rend les logins suivants impossibles : l'ordre d'exécution des
# fichiers ne doit pas décider du résultat des tests.
unlock_admin = _unlock_admin


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


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def _ensure_admin_unlocked():
    """Deverrouille le compte admin avant CHAQUE test.

    `handle_failed_login` incremente `failed_attempts` a chaque mot de passe
    faux : les fichiers qui testent volontairement un refus finissent par
    verrouiller le compte. Le deverrouiller une seule fois par session ne
    suffisait pas, les fixtures de module qui connectent l'admin en direct
    tombaient alors sur un compte verrouille selon l'ORDRE d'execution des
    fichiers.
    """
    _unlock_admin()


@pytest.fixture(scope="function")
def admin_token() -> str:
    """Log in as the TEST-DB admin and return the JWT token.

    Le compte cible vit dans DYNDISPLAY_TEST : le compte admin de production
    n'est jamais utilise ni modifie par la suite.

    Portee FONCTION et non « session » : le jeton d'acces expire au bout de
    ACCESS_TOKEN_EXPIRE_MINUTES, alors que la suite complete dure environ
    40 min. Un jeton de session serait donc mort en cours d'execution, et
    tous les tests suivants echoueraient sur « Token invalide ou expire »
    sans aucun rapport avec ce qu'ils verifient.
    """
    _unlock_admin()
    token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
    assert token is not None, "Failed to obtain admin token – is the API running?"
    return token


@pytest.fixture(scope="function")
def admin_headers(admin_token: str) -> dict:
    return make_headers(admin_token)