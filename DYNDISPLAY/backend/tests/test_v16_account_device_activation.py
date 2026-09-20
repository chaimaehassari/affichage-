"""V16 — Activation par compte et liaison à un appareil (migration 016).

Couvre la spec finale :
- Admin suprême exempté de la sérialisation par appareil.
- Tous les autres comptes (admins normaux ET users) soumis au verrou :
  "X-Device-Id obligatoire", activation par code (account_code), lien
  "1 compte = 1 appareil", révocation par le Super Admin sans re-code
  ni re-consommation de slot, et refus quand le quota postes est atteint.
"""

import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
import requests

BASE_URL = "http://localhost:8000"
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


def _create_client(admin_headers, requires_activation=True):
    user_code = f"V16{_uid()}"
    login = f"v16client_{_uid()}"
    payload = {
        "user_code": user_code,
        "login": login,
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "profile_id": 2,
        "is_active": True,
        "requires_activation": requires_activation,
        "zones": [],
        "permissions": [],
    }
    r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    return {
        "user_code": user_code,
        "login": login,
        "account_code": body.get("account_code"),
        "user_id": body.get("user_id"),
    }


def _find_user(admin_headers, login):
    users = _api("GET", "/api/v1/users", headers=admin_headers).json().get("users", [])
    for u in users:
        if u["login"] == login:
            return u
    return None


def _delete_user(admin_headers, user_id):
    if user_id:
        _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)


def _generate_activation_code(account_code, expires_at=None):
    from app.core.license_utils import generate_activation_code

    return generate_activation_code(account_code, expires_at=expires_at)


def _activate_account(login, account_code, device=DEV1, expires_at=None):
    code = _generate_activation_code(account_code, expires_at=expires_at)
    return _api(
        "POST", "/api/v1/auth/activate-account",
        json={"login": login, "activation_code": code},
        headers={"X-Device-Id": device},
    )


def _login(login, user_code, device=None, password=TEST_PASSWORD):
    body = {"login": login, "password": password}
    if user_code:
        body["client_code"] = user_code
    headers = {}
    if device:
        headers["X-Device-Id"] = device
    return _api("POST", "/api/v1/auth/login", json=body, headers=headers)


def _admin_headers(req_token):
    return {"Authorization": f"Bearer {req_token}", "X-Device-Id": DEV1}


def _activated_count():
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM users
            WHERE requires_activation = FALSE AND COALESCE(is_superadmin, FALSE) = FALSE
            """
        ).fetchone()
        return row[0]


def _account_db(login):
    with psycopg.connect(DB_URL) as conn:
        row = conn.execute(
            """
            SELECT user_id, account_code, requires_activation, authorized_device_id, is_superadmin
            FROM users WHERE login = %s
            """,
            (login,),
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "account_code": row[1],
            "requires_activation": row[2],
            "authorized_device_id": row[3],
            "is_superadmin": row[4],
        }


@pytest.mark.v16
class TestAccountDeviceActivation:

# V16.01 — L'admin suprême est totalement exempté (mécanisme JJMMAAAA)
    # et le login mot de passe sans header X-Device-Id fonctionne toujours.
    def test_v16_01_superadmin_exempt(self):
        from datetime import datetime as _dt
        r = _login("admin", "", device=None, password=ADMIN_PASSWORD)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["is_superadmin"] is True

        day_code = _dt.now().astimezone().strftime("%d%m%Y") + "X7K9"
        r2 = _login("admin", "", device=None, password=day_code)
        assert r2.status_code == 200, r2.text
        assert r2.json()["user"]["is_superadmin"] is True

    # V16.02 — POST /users expose account_code et requires_activation pour les nouveaux comptes
    def test_v16_02_create_user_exposes_account_code(self, admin_headers):
        c = _create_client(admin_headers)
        try:
            assert c["account_code"], "account_code absent de la réponse POST /users"
            assert len(c["account_code"]) >= 4
            assert c["user_id"]
            u = _find_user(admin_headers, c["login"])
            assert u is not None
        finally:
            _delete_user(admin_headers, _find_user(admin_headers, c["login"])["user_id"])

    # V16.03 — Compte non activé : 400 sans X-Device-Id, puis 403 avec account_code,
    # quel que soit l'appareil présenté (rien n'est lié tant que le compte n'est pas activé).
    def test_v16_03_unactivated_login_blocked(self, admin_headers):
        c = _create_client(admin_headers)
        u = _find_user(admin_headers, c["login"])
        try:
            r = _login(c["login"], c["user_code"], device=None)
            assert r.status_code == 400
            assert "X-Device-Id" in r.json()["detail"]

            for device in (DEV1, DEV2):
                r = _login(c["login"], c["user_code"], device=device)
                assert r.status_code == 403, r.text
                detail = r.json()["detail"]
                assert detail["code"] == "account_activation_required"
                assert detail["account_code"] == c["account_code"]
        finally:
            _delete_user(admin_headers, u["user_id"])

    # V16.04 — Activation valide → lien à l'appareil ; un autre appareil est bloqué ;
    # un nouvel échange de code transfère le lien.
    def test_v16_04_activation_binds_device(self, admin_headers):
        c = _create_client(admin_headers)
        u = _find_user(admin_headers, c["login"])
        try:
            r = _activate_account(c["login"], c["account_code"], device=DEV1)
            assert r.status_code == 200, r.text
            assert r.json()["success"] is True

            r = _login(c["login"], c["user_code"], device=DEV1)
            assert r.status_code == 200, r.text
            me = r.json()["user"]
            assert me["requires_activation"] is False
            assert me["authorized_device_id"] == DEV1
            assert me["account_code"] == c["account_code"]

            # Un autre appareil ne peut pas prendre la session
            r = _login(c["login"], c["user_code"], device=DEV2)
            assert r.status_code == 403, r.text
            detail = r.json()["detail"]
            assert detail["code"] == "device_change_activation_required"
            assert detail["account_code"] == c["account_code"]

            # L'utilisateur re-exécute l'application sur DEV2 avec un code d'activation
            r = _activate_account(c["login"], c["account_code"], device=DEV2)
            assert r.status_code == 200, r.text
            r = _login(c["login"], c["user_code"], device=DEV2)
            assert r.status_code == 200, r.text
            assert r.json()["user"]["authorized_device_id"] == DEV2

            # DEV1 est maintenant exclu
            r = _login(c["login"], c["user_code"], device=DEV1)
            assert r.status_code == 403
        finally:
            _delete_user(admin_headers, u["user_id"])

    # V16.05 — Codes invalides / autre compte / expiré
    def test_v16_05_invalid_codes(self, admin_headers):
        a = _create_client(admin_headers)
        b = _create_client(admin_headers)
        ua = _find_user(admin_headers, a["login"])
        ub = _find_user(admin_headers, b["login"])
        try:
            r = _api("POST", "/api/v1/auth/activate-account",
                     json={"login": a["login"], "activation_code": "ZZZZZ-ZZZZZ-ZZZZZ-ZZZZZ"},
                     headers={"X-Device-Id": DEV1})
            assert r.status_code == 400
            assert "invalide" in r.json()["detail"]

            other_code = _generate_activation_code(b["account_code"])
            r = _api("POST", "/api/v1/auth/activate-account",
                     json={"login": a["login"], "activation_code": other_code},
                     headers={"X-Device-Id": DEV1})
            assert r.status_code == 400
            assert "ne correspond pas" in r.json()["detail"]

            past = datetime.now(timezone.utc) - timedelta(days=1)
            expired = _generate_activation_code(a["account_code"], expires_at=past)
            r = _api("POST", "/api/v1/auth/activate-account",
                     json={"login": a["login"], "activation_code": expired},
                     headers={"X-Device-Id": DEV1})
            assert r.status_code == 400
            assert "expiré" in r.json()["detail"]

            # Toujours bloqué après tous les essais invalides
            r = _login(a["login"], a["user_code"], device=DEV1)
            assert r.status_code == 403
        finally:
            _delete_user(admin_headers, ua["user_id"])
            _delete_user(admin_headers, ub["user_id"])

    # V16.06 — Quota postes du client atteint : l'activation est refusée sans consommation.
    def test_v16_06_quota_blocked(self, admin_headers):
        qcode = f"V16Q{_uid()}"
        login = f"v16q_{_uid()}"
        with psycopg.connect(DB_URL) as conn:
            conn.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 5, 0)",
                (qcode, f"Client {qcode}"),
            )
        user_id = None
        try:
            r = _api("POST", "/api/v1/users", json={
                "user_code": qcode,
                "login": login,
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
                "profile_id": 2,
                "is_active": True,
                "requires_activation": True,
                "zones": [],
                "permissions": [],
            }, headers=admin_headers)
            assert r.status_code == 201, r.text
            account_code = r.json()["account_code"]
            user_id = _find_user(admin_headers, login)["user_id"]

            # Quota du client = 0 → refus, sans consommation de slot.
            r = _activate_account(login, account_code, device=DEV1)
            assert r.status_code == 400, r.text
            assert "Quota" in r.json()["detail"] and "fournisseur" in r.json()["detail"]

            db = _account_db(login)
            assert db["requires_activation"] is True
            assert db["authorized_device_id"] is None
            r = _login(login, qcode, device=DEV1)
            assert r.status_code == 403

            # Augmentation de la licence du client → l'activation passe.
            with psycopg.connect(DB_URL) as conn:
                conn.execute(
                    "UPDATE clients SET license_posts = 5 WHERE code_client = %s", (qcode,)
                )
            r = _activate_account(login, account_code, device=DEV1)
            assert r.status_code == 200, r.text
            r = _login(login, qcode, device=DEV1)
            assert r.status_code == 200, r.text
        finally:
            if user_id is not None:
                _delete_user(admin_headers, user_id)
            with psycopg.connect(DB_URL) as conn:
                conn.execute("DELETE FROM clients WHERE code_client = %s", (qcode,))

    # V16.07 — Révocation par le Super Admin : libère l'appareil SANS réactiver le
    # compte ni re-consommer un slot ; le prochain appareil est autorisé d'office.
    def test_v16_07_revoke_device(self, admin_headers):
        c = _create_client(admin_headers)
        u = _find_user(admin_headers, c["login"])
        activated_before = _activated_count()
        try:
            r = _activate_account(c["login"], c["account_code"], device=DEV1)
            assert r.status_code == 200, r.text
            assert _activated_count() == activated_before + 1

            r = _login(c["login"], c["user_code"], device=DEV1)
            assert r.status_code == 200, r.text
            token = r.json()["access_token"]
            assert r.json()["user"]["authorized_device_id"] == DEV1

            # Seul le Super Admin voit /settings/accounts/devices
            r = _api("GET", "/api/v1/settings/accounts/devices", headers=_admin_headers(token))
            assert r.status_code == 403
            r = _api("GET", "/api/v1/settings/accounts/devices", headers=admin_headers)
            assert r.status_code == 200, r.text
            body = r.json()
            logins = [a["login"] for a in body["accounts"]]
            assert c["login"] in logins
            assert "admin" not in logins  # l'admin suprême est exclu de la liste
            mine = next(a for a in body["accounts"] if a["login"] == c["login"])
            assert mine["requires_activation"] is False
            assert mine["authorized_device_id"] == DEV1

            # Révocation
            rid = u["user_id"]
            r = _api("POST", f"/api/v1/settings/accounts/{rid}/revoke-device", headers=admin_headers)
            assert r.status_code == 200, r.text
            assert "automatiquement autorisé" in r.json()["message"]

            body = _api("GET", "/api/v1/settings/accounts/devices", headers=admin_headers).json()
            mine = next(a for a in body["accounts"] if a["login"] == c["login"])
            assert mine["authorized_device_id"] is None
            assert mine["requires_activation"] is False  # pas de re-code
            assert _activated_count() == activated_before + 1  # slot conservé

            # Nouvel appareil : liaison silencieuse immédiate, sans code
            r = _login(c["login"], c["user_code"], device=DEV2)
            assert r.status_code == 200, r.text
            assert r.json()["user"]["authorized_device_id"] == DEV2

            # L'ancien appareil est exclu
            r = _login(c["login"], c["user_code"], device=DEV1)
            assert r.status_code == 403
        finally:
            _delete_user(admin_headers, u["user_id"])

    # V16.08 — Un admin classique (non superadmin) est soumis au même verrou.
    def test_v16_08_normal_admin_gated_and_revocable(self, admin_headers):
        login = f"v16admin_{_uid()}"
        created = _api("POST", "/api/v1/admins", headers=admin_headers, json={
            "login": login,
            "email": None,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "is_active": True,
            "client_codes": [],
        })
        assert created.status_code == 201, created.text
        admin_id = created.json()["user_id"]
        try:
            db = _account_db(login)
            assert db is not None
            assert db["is_superadmin"] is False
            assert db["requires_activation"] is True
            account_code = db["account_code"]

            r = _login(login, "", device=None)
            assert r.status_code == 400
            assert "X-Device-Id" in r.json()["detail"]

            r = _login(login, "", device=DEV1)
            assert r.status_code == 403, r.text
            detail = r.json()["detail"]
            assert detail["code"] == "account_activation_required"
            assert detail["account_code"] == account_code

            r = _activate_account(login, account_code, device=DEV1)
            assert r.status_code == 200, r.text

            r = _login(login, "", device=DEV1)
            assert r.status_code == 200, r.text
            me = r.json()["user"]
            assert me["profile_name"] == "Administrateur"
            assert me["is_superadmin"] is False
            assert me["requires_activation"] is False
            assert me["authorized_device_id"] == DEV1

            # Révocable par le Super Admin (compte admin normal inclus)
            r = _api("POST", f"/api/v1/settings/accounts/{admin_id}/revoke-device", headers=admin_headers)
            assert r.status_code == 200
            r = _login(login, "", device=DEV2)
            assert r.status_code == 200, r.text
            assert r.json()["user"]["authorized_device_id"] == DEV2
        finally:
            _api("DELETE", f"/api/v1/admins/{admin_id}", headers=admin_headers)