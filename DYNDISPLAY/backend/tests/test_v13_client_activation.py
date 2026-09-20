import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


TEST_PASSWORD = "Test@1234"


@pytest.mark.v13
class TestClientActivation:

    def _create_client(self, admin_headers, requires_activation=True):
        user_code = f"ACT{_uid()}"
        login = f"clientact_{_uid()}"
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
        account_code = r.json().get("account_code")
        # Le compte est créé en attente d'activation par appareil : on lui fournit
        # un code d'activation (application mobile simulée) avant de se connecter.
        from app.core.license_utils import generate_activation_code
        act_code = generate_activation_code(account_code)
        act = _api("POST", "/api/v1/auth/activate-account",
                   json={"login": login, "activation_code": act_code},
                   headers={"X-Device-Id": "pytest-device-0001"})
        assert act.status_code == 200, act.text
        return {"user_code": user_code, "login": login}

    def _find_user(self, admin_headers, login):
        users = _api("GET", "/api/v1/users", headers=admin_headers).json().get("users", [])
        for u in users:
            if u["login"] == login:
                return u
        return None

    def _delete_user(self, admin_headers, user_id):
        _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)

    def _login(self, login, user_code):
        r = _api("POST", "/api/v1/auth/login", json={
            "login": login, "password": TEST_PASSWORD, "client_code": user_code,
        }, headers={"X-Device-Id": "pytest-device-0001"})
        assert r.status_code == 200, r.text
        return r.json()

    # ACT-01: un client marqué "à activer" est créé non activé, et voit son état dans /auth/me
    def test_act01_client_created_unactivated(self, admin_headers):
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        assert u.get("is_activated") is False
        session = self._login(c["login"], c["user_code"])
        assert session["user"]["is_activated"] is False
        assert session["user"]["user_code"] == c["user_code"]
        self._delete_user(admin_headers, u["user_id"])

    # ACT-02: compte non activé -> accès aux données bloqué (403)
    def test_act02_unactivated_blocked(self, admin_headers):
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        r = _api("GET", "/api/v1/users", headers=headers)
        assert r.status_code == 403
        assert "sérialisation" in r.json().get("detail", "")
        # Probe non perceptif : change-password (route sans permission) doit être 403 tant que non activé
        probe = _api("POST", "/api/v1/settings/change-password", headers=headers, json={
            "current_password": "Wrong@1234", "new_password": "NewPass@1234",
        })
        assert probe.status_code == 403
        self._delete_user(admin_headers, u["user_id"])

    # ACT-03: code invalide rejeté
    def test_act03_invalid_code(self, admin_headers):
        from app.core.license_utils import generate_license
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        r = _api("POST", "/api/v1/auth/activate", json={"code": "ZZZZZ-ZZZZZ-ZZZZZ-ZZZZZ"}, headers=headers)
        assert r.status_code == 400
        assert "invalide" in r.json().get("detail", "")
        assert generate_license is not None
        self._delete_user(admin_headers, u["user_id"])

    # ACT-04: code valide mais pour un autre n° client -> refusé
    def test_act04_code_for_another_client_rejected(self, admin_headers):
        from app.core.license_utils import generate_license
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        wrong_code = generate_license(f"OTHER{_uid()}", 5, 200)
        r = _api("POST", "/api/v1/auth/activate", json={"code": wrong_code}, headers=headers)
        assert r.status_code == 400
        assert "ne correspond pas" in r.json().get("detail", "")
        self._delete_user(admin_headers, u["user_id"])

    # ACT-05: code valide pour SON n° client -> activation, limites stockées, accès débloqué
    def test_act05_valid_code_activates(self, admin_headers):
        from app.core.license_utils import generate_license
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        code = generate_license(c["user_code"], 12, 350)
        r = _api("POST", "/api/v1/auth/activate", json={"code": code}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_activated"] is True
        assert body["sites_limit"] == 12
        assert body["posts_limit"] == 350
        assert body["activated_at"] is not None
        # L'accès aux données est débloqué (probe change-password : 400 et non plus 403)
        probe = _api("POST", "/api/v1/settings/change-password", headers=headers, json={
            "current_password": "Wrong@1234", "new_password": "NewPass@1234",
        })
        assert probe.status_code == 400
        # /auth/me reflète l'activation
        me = _api("GET", "/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["is_activated"] is True
        self._delete_user(admin_headers, u["user_id"])

    # ACT-06: un code valide soumis sur un compte déjà activé met à jour les limites (nouveau code de sérialisation),
#          en conservant la date d'activation d'origine
    def test_act06_valid_code_updates_limits(self, admin_headers):
        from app.core.license_utils import generate_license
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        code_a = generate_license(c["user_code"], 12, 350)
        first = _api("POST", "/api/v1/auth/activate", json={"code": code_a}, headers=headers)
        assert first.status_code == 200, first.text
        activated_at = first.json()["activated_at"]

        code_b = generate_license(c["user_code"], 20, 500)
        r = _api("POST", "/api/v1/auth/activate", json={"code": code_b}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_activated"] is True
        assert body["sites_limit"] == 20
        assert body["posts_limit"] == 500
        assert body["activated_at"] == activated_at
        me = _api("GET", "/api/v1/auth/me", headers=headers)
        assert me.json()["sites_limit"] == 20
        assert me.json()["posts_limit"] == 500
        self._delete_user(admin_headers, u["user_id"])

    # ACT-06b: un code invalide soumis pour une modification ne change rien
    def test_act06b_invalid_code_does_not_change_limits(self, admin_headers):
        from app.core.license_utils import generate_license
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        code_a = generate_license(c["user_code"], 12, 350)
        assert _api("POST", "/api/v1/auth/activate", json={"code": code_a}, headers=headers).status_code == 200
        r = _api("POST", "/api/v1/auth/activate", json={"code": "ZZZZZ-ZZZZZ-ZZZZZ-ZZZZZ"}, headers=headers)
        assert r.status_code == 400
        me = _api("GET", "/api/v1/auth/me", headers=headers)
        assert me.json()["sites_limit"] == 12
        assert me.json()["posts_limit"] == 350
        self._delete_user(admin_headers, u["user_id"])

    # ACT-07: un compte normal (sans demande d'activation) reste activé par défaut
    def test_act07_default_account_activated(self, admin_headers):
        c = self._create_client(admin_headers, requires_activation=False)
        u = self._find_user(admin_headers, c["login"])
        assert u.get("is_activated") is True
        self._delete_user(admin_headers, u["user_id"])

    # ACT-08: l'admin peut rétro-activer/désactiver un compte via le flag requires_activation
    def test_act08_admin_toggles_activation(self, admin_headers):
        c = self._create_client(admin_headers, requires_activation=True)
        u = self._find_user(admin_headers, c["login"])
        assert u.get("is_activated") is False
        r = _api("PUT", f"/api/v1/users/{u['user_id']}", headers=admin_headers, json={
            "login": c["login"],
            "user_code": c["user_code"],
            "profile_id": 2,
            "is_active": True,
            "requires_activation": False,
            "zones": [],
            "permissions": [],
        })
        assert r.status_code == 200, r.text
        detail = _api("GET", f"/api/v1/users/{u['user_id']}", headers=admin_headers)
        assert detail.json()["is_activated"] is True
        self._delete_user(admin_headers, u["user_id"])

    # ACT-09: après activation, une reconnexion redonne un accès normal (plus d'écran de sérialisation)
    def test_act09_reactivated_relogin_normal_access(self, admin_headers):
        from app.core.license_utils import generate_license
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        code = generate_license(c["user_code"], 4, 80)
        r = _api("POST", "/api/v1/auth/activate", json={"code": code}, headers=headers)
        assert r.status_code == 200, r.text

        logout = _api("POST", "/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 200, logout.text

        session2 = self._login(c["login"], c["user_code"])
        assert session2["user"]["is_activated"] is True
        assert session2["user"]["sites_limit"] == 4
        assert session2["user"]["posts_limit"] == 80
        headers2 = {"Authorization": f"Bearer {session2['access_token']}"}
        probe = _api("POST", "/api/v1/settings/change-password", headers=headers2, json={
            "current_password": "Wrong@1234", "new_password": "NewPass@1234",
        })
        assert probe.status_code == 400
        self._delete_user(admin_headers, u["user_id"])

    # ACT-10: compte non activé qui "recharge" (re-fetch /auth/me) reste bloqué ; la session reste valide mais verrouillée
    def test_act10_reload_stays_blocked(self, admin_headers):
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        me = _api("GET", "/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["is_activated"] is False
        assert me.json()["login"] == c["login"]
        r = _api("GET", "/api/v1/sites", headers=headers)
        assert r.status_code in (403, 404), r.text
        if r.status_code == 403:
            assert "sérialisation" in r.json().get("detail", "")
        self._delete_user(admin_headers, u["user_id"])