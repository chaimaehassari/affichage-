"""Activation de compte SUPPRIMEE (contrat metier 2026-10).

Tout nouveau compte (client ou admin) est cree immediatement actif.
Aucun code d'activation n'est demande au login : on verifie le mot de passe
(+ code client pour les profils non-Administrateur), et le changement de mot
de passe est impose a la premiere connexion (`must_change_password`).

Les quotas de licences sites/postes sont geres par le Super Admin via
`PUT /clients/{code}/license` (client serialization).
"""
import uuid

import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    headers = kwargs.get("headers") or {}
    if "Authorization" in headers:
        kwargs = {**kwargs, "headers": {"X-Device-Id": "pytest-device-0001", **headers}}
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


TEST_PASSWORD = "Test@1234"

# Codes clients cree par les tests de ce fichier (voir _create_client).
_TEMP_CLIENTS: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup_temp_clients():
    """Supprime les clients temporaires crees par les tests."""
    yield
    if not _TEMP_CLIENTS:
        return
    import psycopg
    from tests._test_config import get_test_db_url
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clients WHERE code_client = ANY(%s)", (_TEMP_CLIENTS,))
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.clear()


def _create_client_row(user_code: str) -> str:
    """Cree un vrai client dont le `code_client` est le `user_code` du compte."""
    import psycopg
    from tests._test_config import get_test_db_url
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clients (code_client, nom_client, license_sites, license_posts)
                VALUES (%s, %s, 10, 50)
                """,
                (user_code, f"Client {user_code}"),
            )
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.append(user_code)
    return user_code


@pytest.mark.v13
class TestClientActivation:
    """Regression de la suppression de l'activation de compte."""

    def _create_client(self, admin_headers, extra=None):
        user_code = f"ACT{_uid()}"
        _create_client_row(user_code)
        login = f"clientact_{_uid()}"
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
        payload.update(extra or {})
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code == 201, r.text
        body = r.json()
        return {
            "user_code": user_code,
            "login": login,
            "user_id": body["user_id"],
        }

    def _find_user(self, admin_headers, login):
        users = _api("GET", "/api/v1/users", headers=admin_headers).json().get("users", [])
        for u in users:
            if u["login"] == login:
                return u
        return None

    def _delete_user(self, admin_headers, user_id):
        _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)

    def _login(self, login, user_code):
        return _api("POST", "/api/v1/auth/login", json={
            "login": login, "password": TEST_PASSWORD, "client_code": user_code,
        }, headers={"X-Device-Id": "pytest-device-0001"})

    def _probe_access(self, token):
        """Probe non perceptif : change-password renvoie 400 (acces autorise,
        mot de passe courant faux) et non 403 (acces bloque par activation)."""
        return _api("POST", "/api/v1/settings/change-password",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"current_password": "Wrong@1234",
                          "new_password": "NewPass@1234"})

    # ACT-01: tout compte cree est immediatement actif et se connecte.
    def test_act01_account_always_created_active(self, admin_headers):
        c = self._create_client(admin_headers)
        try:
            u = self._find_user(admin_headers, c["login"])
            assert u.get("is_active") is True
            session = self._login(c["login"], c["user_code"])
            assert session.status_code == 200, session.text
            assert session.json()["user"]["must_change_password"] is True
        finally:
            self._delete_user(admin_headers, c["user_id"])

    # ACT-01b: un champ d'activation residuel est ignore (compat) et le compte
    # cree est immediatement actif.
    def test_act01b_legacy_activation_field_ignored(self, admin_headers):
        c = self._create_client(admin_headers, {"requires_activation": True})
        try:
            u = self._find_user(admin_headers, c["login"])
            assert u.get("is_active") is True
            session = self._login(c["login"], c["user_code"])
            assert session.status_code == 200, session.text
            assert session.json()["user"]["must_change_password"] is True
        finally:
            self._delete_user(admin_headers, c["user_id"])

    # ACT-02: le login ne demande JAMAIS de code d'activation ; l'acces est direct.
    def test_act02_no_activation_code_needed(self, admin_headers):
        c = self._create_client(admin_headers)
        try:
            session = self._login(c["login"], c["user_code"])
            assert session.status_code == 200, session.text
            detail = session.json() if session.status_code != 200 else None
            assert "account_activation_required" not in str(detail)
            token = session.json()["access_token"]
            probe = self._probe_access(token)
            assert probe.status_code == 400, probe.text
        finally:
            self._delete_user(admin_headers, c["user_id"])

    # ACT-03: la premiere connexion impose le changement de mot de passe.
    def test_act03_first_login_must_change_password(self, admin_headers):
        c = self._create_client(admin_headers)
        try:
            session = self._login(c["login"], c["user_code"])
            assert session.status_code == 200, session.text
            assert session.json()["user"]["must_change_password"] is True
        finally:
            self._delete_user(admin_headers, c["user_id"])

    # ACT-04: les quotas de licences du client restent gerables
    # (PUT /clients/{code}/license), et le compte se connecte sans activation.
    def test_act04_client_license_quotas(self, admin_headers):
        c = self._create_client(admin_headers)
        try:
            r = _api("PUT", f"/api/v1/clients/{c['user_code']}/license",
                     json={"license_sites": 12, "license_posts": 350},
                     headers=admin_headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["license_sites"] == 12
            assert body["license_posts"] == 350

            session = self._login(c["login"], c["user_code"])
            assert session.status_code == 200, session.text
        finally:
            self._delete_user(admin_headers, c["user_id"])

    # ACT-05: quotas invalides rejetes (valeurs negatives).
    def test_act05_invalid_client_license_quotas(self, admin_headers):
        c = self._create_client(admin_headers)
        try:
            r = _api("PUT", f"/api/v1/clients/{c['user_code']}/license",
                     json={"license_sites": -1, "license_posts": 350},
                     headers=admin_headers)
            assert r.status_code == 422, r.text
        finally:
            self._delete_user(admin_headers, c["user_id"])

    # ACT-06: un admin cree via POST /admins se connecte sans activation.
    def test_act06_admin_created_active_and_logs_in(self, admin_headers):
        login = f"actadm_{_uid()}"
        payload = {
            "login": login,
            "email": None,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "is_active": True,
            "client_codes": [],
        }
        created = _api("POST", "/api/v1/admins", json=payload, headers=admin_headers)
        assert created.status_code == 201, created.text
        admin_id = created.json()["user_id"]
        try:
            r = _api("POST", "/api/v1/auth/login",
                     json={"login": login, "password": TEST_PASSWORD},
                     headers={"X-Device-Id": "pytest-device-0001"})
            assert r.status_code == 200, r.text
            user = r.json()["user"]
            assert user["profile_name"] == "Administrateur"
            assert user["must_change_password"] is True
        finally:
            _api("DELETE", f"/api/v1/admins/{admin_id}", headers=admin_headers)