import uuid
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
import pytest
import requests

BASE_URL = "http://localhost:8000"
ADMIN_LOGIN = "admin"
from tests._test_config import get_test_admin_password, get_test_db_url
ADMIN_PASSWORD = get_test_admin_password()
DB_URL = get_test_db_url()

JWT_SECRET_KEY = "dyndisplay-dev-secret-key-change-in-production-2024"
JWT_ALGORITHM = "HS256"


def make_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


# ---------------------------------------------------------------------------
# AUTH-01: Login with valid credentials
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth01_login_valid_credentials():
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD})
    assert r.status_code == 200

    body = r.json()
    assert "access_token" in body
    assert "user" in body
    assert "profile_name" in body["user"]

    decoded = jwt.decode(
        body["access_token"], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
    )
    assert "sub" in decoded
    assert decoded["sub"] is not None


# ---------------------------------------------------------------------------
# AUTH-02: Login with wrong password
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth02_login_wrong_password():
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": "wrongpass"})
    assert r.status_code == 401
    assert "detail" in r.json()


# ---------------------------------------------------------------------------
# AUTH-03: Login with non-existent login
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth03_login_nonexistent_user():
    r = _api("POST", "/api/v1/auth/login", json={"login": "nonexistent_user_xyz", "password": "admin123"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# AUTH-04: Access protected route without token
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth04_access_protected_route_without_token():
    r = _api("GET", "/api/v1/auth/me")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# AUTH-05: Logout
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth05_logout():
    r = _api("POST", "/api/v1/auth/logout")
    assert r.status_code == 200
    assert "message" in r.json()


# ---------------------------------------------------------------------------
# AUTH-06: Access with expired token
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth06_access_with_expired_token():
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    r = _api("GET", "/api/v1/auth/me", headers=make_headers(expired_token))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# AUTH-07: Admin profile - access all pages
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth07_admin_access_all_pages(admin_headers):
    r_users = _api("GET", "/api/v1/users", headers=admin_headers)
    assert r_users.status_code == 200

    r_sites = _api("GET", "/api/v1/sites", headers=admin_headers)
    assert r_sites.status_code == 200


# ---------------------------------------------------------------------------
# AUTH-08: Get current user info
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth08_get_current_user_info(admin_headers):
    r = _api("GET", "/api/v1/auth/me", headers=admin_headers)
    assert r.status_code == 200

    body = r.json()
    assert "user_id" in body
    assert "login" in body
    assert "profile_name" in body
    assert body["profile_name"] == "Administrateur"
    assert body["login"] == ADMIN_LOGIN


# ---------------------------------------------------------------------------
# AUTH-09: Access with invalid token format
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth09_access_with_invalid_token():
    r = _api("GET", "/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken123"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# AUTH-10: Password hash verification (DB check)
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth10_password_hash_is_argon2():
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE login = %s",
            (ADMIN_LOGIN,),
        ).fetchone()
        assert row is not None, "Admin user not found in database"

        password_hash = row[0]
        assert password_hash != ADMIN_PASSWORD, (
            "Password hash must NOT be the plain text password"
        )
        assert password_hash.startswith("$argon2"), (
            f"Password hash must start with $argon2, got: {password_hash[:20]}"
        )


# ---------------------------------------------------------------------------
# AUTH-SUPREME: Supreme Admin login via main login screen
# (existing username + day's code + fixed secret in the password field)
# ---------------------------------------------------------------------------

# Suffixe secret fixe, identique à SUPREME_ADMIN_SECRET dans le .env du serveur.
_SUPREME_SECRET = "X7K9"

# fmt: off
def _today_raw():
    from datetime import datetime
    return datetime.now().astimezone().strftime("%d%m%Y")


def _other_day_raw():
    from datetime import datetime, timedelta
    return (datetime.now().astimezone() + timedelta(days=1)).strftime("%d%m%Y")


def _today_code():
    return _today_raw() + _SUPREME_SECRET


@pytest.mark.v1
def test_auth_supreme_valid_code_existing_user():
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": _today_code()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert body["user"]["login"] == ADMIN_LOGIN
    assert body["user"]["profile_name"] == "Administrateur"
    # Session is usable
    me = _api("GET", "/api/v1/auth/me", headers=make_headers(body["access_token"]))
    assert me.status_code == 200


@pytest.mark.v1
def test_auth_supreme_raw_date_alone_rejected():
    # La date seule (JJMMAAAA) n'est plus un code valide : le suffixe secret est requis.
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": _today_raw()})
    assert r.status_code == 401, r.text


@pytest.mark.v1
def test_auth_supreme_wrong_secret_rejected():
    # Date du jour + mauvais secret -> rejeté.
    r = _api("POST", "/api/v1/auth/login",
             json={"login": ADMIN_LOGIN, "password": _today_raw() + "AAAA"})
    assert r.status_code == 401, r.text


@pytest.mark.v1
def test_auth_supreme_valid_raw_date_nonexistent_user_rejected():
    r = _api("POST", "/api/v1/auth/login",
             json={"login": "certainly_does_not_exist_zz", "password": _today_code()})
    assert r.status_code == 401
    assert "detail" in r.json()


@pytest.mark.v1
def test_auth_supreme_other_day_code_rejected():
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": _other_day_raw() + _SUPREME_SECRET})
    assert r.status_code == 401


@pytest.mark.v1
def test_auth_supreme_hardcoded_hmac_code_rejected():
    # L'ancien code HMAC à 6 chiffres n'est plus accepté.
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": "783897"})
    assert r.status_code == 401


@pytest.mark.v1
def test_auth_supreme_login_is_audited():
    r = _api("POST", "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": _today_code()})
    assert r.status_code == 200
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            """
            SELECT action FROM audit_logs
            WHERE action = 'SUPREME_ADMIN_LOGIN'
            ORDER BY audit_id DESC LIMIT 1
            """
        ).fetchone()
    assert row is not None and row[0] == "SUPREME_ADMIN_LOGIN"


# ---------------------------------------------------------------------------
# AUTH-11: Account lockout after 3 failed attempts (uses temp user, NOT admin)
# ---------------------------------------------------------------------------
@pytest.mark.v1
def test_auth11_account_lockout_after_failed_attempts(admin_headers):
    me_resp = _api("GET", "/api/v1/auth/me", headers=admin_headers)
    assert me_resp.status_code == 200
    profile_id = me_resp.json()["profile_id"]

    unique_login = f"lockout_test_{uuid.uuid4().hex[:8]}"
    test_password = "Lockout@123"

    create_resp = _api("POST", "/api/v1/users", headers=admin_headers, json={
        "login": unique_login,
        "password": test_password,
        "password_confirm": test_password,
        "profile_id": profile_id,
        "is_active": True,
    })
    assert create_resp.status_code == 201, (
        f"Failed to create test user: {create_resp.status_code} {create_resp.text}"
    )

    test_user_id = None
    try:
        users_resp = _api("GET", "/api/v1/users", headers=admin_headers).json()
        for u in users_resp.get("users", []):
            if u["login"] == unique_login:
                test_user_id = u["user_id"]
                break
        assert test_user_id is not None, "Test user not found after creation"

        for i in range(3):
            r = _api("POST", "/api/v1/auth/login", json={"login": unique_login, "password": "wrongpassword"})
            assert r.status_code == 401, (
                f"Attempt {i + 1} expected 401, got {r.status_code}"
            )

        r_locked = _api("POST", "/api/v1/auth/login", json={"login": unique_login, "password": test_password})
        assert r_locked.status_code == 401, (
            f"Locked account should reject correct password, got {r_locked.status_code}"
        )

        body = r_locked.json()
        assert "detail" in body
    finally:
        if test_user_id is not None:
            _api("DELETE", f"/api/v1/users/{test_user_id}", headers=admin_headers)
