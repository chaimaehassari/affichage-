"""V16 — Activation de compte et verrou d'appareil SUPPRIMES (contrat 2026-10).

Plus aucun code d'activation, plus aucun `X-Device-Id` obligatoire : le login
verifie le mot de passe (+ code client pour les profils non-Administrateur),
puis impose le changement de mot de passe a la premiere connexion
(`must_change_password`). Plus aucune notion d'appareil : une session ne
depend pas de l'appareil qui l'a ouverte.
"""

import uuid

import psycopg
import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_admin_password, get_test_db_url
DB_URL = get_test_db_url()
ADMIN_PASSWORD = get_test_admin_password()
TEST_PASSWORD = "Test@1234"
DEV1 = "pytest-v16-device-1"
DEV2 = "pytest-v16-device-2"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _create_client(admin_headers):
    user_code = f"V16{_uid()}"
    login = f"v16client_{_uid()}"
    payload = {
        "user_code": user_code,
        "login": login,
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "profile_id": 2,
        "is_active": True,
        "zones": [],
        "permissions": [],
    }
    r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    return {
        "user_code": user_code,
        "login": login,
        "user_id": body["user_id"],
    }


def _delete_user(admin_headers, user_id):
    if user_id:
        _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)


def _login(login, user_code, device=None, password=TEST_PASSWORD):
    body = {"login": login, "password": password}
    if user_code:
        body["client_code"] = user_code
    headers = {}
    if device:
        headers["X-Device-Id"] = device
    return _api("POST", "/api/v1/auth/login", json=body, headers=headers)


def _user_active_db(login):
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            "SELECT is_active FROM users WHERE login = %s",
            (login,),
        ).fetchone()
        return bool(row and row[0])


@pytest.mark.v16
class TestNoAccountDeviceActivation:

    # V16.01 — Le login n'exige NI code d'activation NI X-Device-Id.
    def test_v16_01_login_password_and_client_code_only(self, admin_headers):
        c = _create_client(admin_headers)
        try:
            for device in (None, DEV1, DEV2):
                r = _login(c["login"], c["user_code"], device=device)
                assert r.status_code == 200, r.text
                assert r.json()["user"]["must_change_password"] is True
                assert "account_activation_required" not in str(r.json())
        finally:
            _delete_user(admin_headers, c["user_id"])

    # V16.02 — POST /users ne renvoie plus AUCUN champ d'activation.
    def test_v16_02_created_account_activation_fields_absent(self, admin_headers):
        c = _create_client(admin_headers)
        try:
            body = _api("GET", f"/api/v1/users/{c['user_id']}",
                        headers=admin_headers).json()
            for field in ("account_code", "requires_activation",
                          "is_activated", "activated_at", "authorized_device_id"):
                assert field not in body, field
            assert _user_active_db(c["login"]) is True
        finally:
            _delete_user(admin_headers, c["user_id"])

    # V16.03 — Aucune session n'est refusee sur un autre appareil.
    def test_v16_03_never_account_activation_required(self, admin_headers):
        c = _create_client(admin_headers)
        try:
            for device in (DEV1, DEV2):
                r = _login(c["login"], c["user_code"], device=device)
                assert r.status_code == 200, r.text
                assert "account_activation_required" not in str(r.json())
                assert "device_change_activation_required" not in str(r.json())
        finally:
            _delete_user(admin_headers, c["user_id"])

    # V16.04 — Une session obtenue sur DEV1 fonctionne depuis DEV2 (plus de
    # verrou d'appareil sur les requetes), et le refresh aussi.
    def test_v16_04_session_and_refresh_any_device(self, admin_headers):
        c = _create_client(admin_headers)
        try:
            r = _login(c["login"], c["user_code"], device=DEV1)
            assert r.status_code == 200, r.text
            token = r.json()["access_token"]
            refresh_token = r.json()["refresh_token"]

            for headers in (
                {"Authorization": f"Bearer {token}", "X-Device-Id": DEV2},
                {"Authorization": f"Bearer {token}"},
            ):
                me = _api("GET", "/api/v1/auth/me", headers=headers)
                assert me.status_code == 200, me.text

            renewed = _api("POST", "/api/v1/auth/refresh",
                           json={"refresh_token": refresh_token},
                           headers={"X-Device-Id": DEV2})
            assert renewed.status_code == 200, renewed.text
            assert "access_token" in renewed.json()
        finally:
            _delete_user(admin_headers, c["user_id"])

    # V16.06 — Admin suprême : login mot de passe et mecanisme JJMMAAAA + X7K9.
    def test_v16_06_superadmin_exempt(self):
        r = _login("admin", "", device=None, password=ADMIN_PASSWORD)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["is_superadmin"] is True

        from datetime import datetime as _dt
        day_code = _dt.now().astimezone().strftime("%d%m%Y") + "X7K9"
        r2 = _login("admin", "", device=None, password=day_code)
        assert r2.status_code == 200, r2.text
        assert r2.json()["user"]["is_superadmin"] is True