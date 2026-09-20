import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


TEST_PASSWORD = "Test@1234"


@pytest.mark.v11
class TestUserEmail:

    def _create_user_with_email(self, admin_headers, email=None, suffix="001"):
        login = f"emailuser_{_uid()}_{suffix}"
        payload = {
            "user_code": f"EC{_uid()}",
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "zones": [1, 2],
            "permissions": [],
        }
        if email:
            payload["email"] = email
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code == 201, r.text
        return login

    def _find_user(self, admin_headers, login):
        users = _api("GET", "/api/v1/users", headers=admin_headers).json().get("users", [])
        for u in users:
            if u["login"] == login:
                return u
        return None

    def _delete_user(self, admin_headers, user_id):
        _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)

    # EMAIL-01: Create user with email -> email saved & returned in list
    def test_email01_create_with_email(self, admin_headers):
        email = f"{_uid().lower()}@example.com"
        login = self._create_user_with_email(admin_headers, email=email, suffix="001")
        u = self._find_user(admin_headers, login)
        assert u is not None
        assert u.get("email") == email.lower()
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-02: User detail returns email
    def test_email02_detail_returns_email(self, admin_headers):
        email = f"{_uid().lower()}@example.com"
        login = self._create_user_with_email(admin_headers, email=email, suffix="002")
        u = self._find_user(admin_headers, login)
        detail = _api("GET", f"/api/v1/users/{u['user_id']}", headers=admin_headers)
        assert detail.status_code == 200
        assert detail.json().get("email") == email.lower()
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-03: /auth/me exposes email after login
    def test_email03_me_exposes_email(self, admin_headers):
        email = f"{_uid().lower()}@example.com"
        login = f"emailuser_{_uid()}_003"
        payload = {
            "user_code": f"EC{_uid()}",
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "zones": [1, 2],
            "permissions": [],
            "email": email,
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code == 201, r.text
        account_code = r.json().get("account_code")
        u = self._find_user(admin_headers, login)

        from app.core.license_utils import generate_activation_code
        act_code = generate_activation_code(account_code)
        act = _api("POST", "/api/v1/auth/activate-account",
                   json={"login": login, "activation_code": act_code},
                   headers={"X-Device-Id": "pytest-device-0001"})
        assert act.status_code == 200, act.text

        r = _api("POST", "/api/v1/auth/login", json={"login": login, "password": TEST_PASSWORD, "client_code": u["user_code"]},
                 headers={"X-Device-Id": "pytest-device-0001"})
        assert r.status_code == 200
        assert r.json()["user"].get("email") == email.lower()

        u = self._find_user(admin_headers, login)
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-04: Update email
    def test_email04_update_email(self, admin_headers):
        login = self._create_user_with_email(admin_headers, email="old@example.com", suffix="004")
        u = self._find_user(admin_headers, login)
        new_email = "new@example.com"
        r = _api("PUT", f"/api/v1/users/{u['user_id']}", headers=admin_headers, json={
            "login": login,
            "email": new_email,
            "profile_id": 2,
            "is_active": True,
            "zones": [1],
            "permissions": [],
        })
        assert r.status_code == 200, r.text
        detail = _api("GET", f"/api/v1/users/{u['user_id']}", headers=admin_headers).json()
        assert detail.get("email") == new_email
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-05: Invalid email rejected
    def test_email05_invalid_email_rejected(self, admin_headers):
        r = _api("POST", "/api/v1/users", headers=admin_headers, json={
            "login": f"bad_mail_{_uid()}",
            "email": "not-an-email",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "zones": [],
            "permissions": [],
        })
        assert r.status_code == 422

    # EMAIL-06: Duplicate email rejected
    def test_email06_duplicate_email_rejected(self, admin_headers):
        email = f"{_uid().lower()}@example.com"
        login = self._create_user_with_email(admin_headers, email=email, suffix="006")
        u = self._find_user(admin_headers, login)

        r = _api("POST", "/api/v1/users", headers=admin_headers, json={
            "login": f"dup_{_uid()}",
            "email": email,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "zones": [],
            "permissions": [],
        })
        assert r.status_code == 400
        assert "e-mail" in r.json().get("detail", "")
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-07: Forgot-password for unknown account -> generic message
    def test_email07_forgot_unknown(self, admin_headers):
        r = _api("POST", "/api/v1/auth/forgot-password", json={"login": "definitely_not_exists"})
        assert r.status_code == 200
        assert "Si ce compte existe" in r.json().get("message", "")

    # EMAIL-08: Forgot-password for account without email -> helpful message
    def test_email08_forgot_no_email(self, admin_headers):
        login = self._create_user_with_email(admin_headers, email=None, suffix="008")
        u = self._find_user(admin_headers, login)
        r = _api("POST", "/api/v1/auth/forgot-password", json={"login": login})
        assert r.status_code == 200
        assert "Aucune adresse e-mail" in r.json().get("message", "")
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-09: Forgot-password by LOGIN with existing email reaches the send stage
    #   (returns 200 + generic msg if SMTP configured, else 400 with SMTP detail)
    def test_email09_forgot_by_login(self, admin_headers):
        email = f"{_uid().lower()}@example.com"
        login = self._create_user_with_email(admin_headers, email=email, suffix="009")
        u = self._find_user(admin_headers, login)
        r = _api("POST", "/api/v1/auth/forgot-password", json={"login": login})
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert "e-mail de réinitialisation" in r.json().get("message", "")
        else:
            assert "SMTP" in r.json().get("detail", "") or "e-mail" in r.json().get("detail", "")
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-10: Forgot-password by EMAIL address reaches the send stage
    def test_email10_forgot_by_email(self, admin_headers):
        email = f"{_uid().lower()}@example.com"
        login = self._create_user_with_email(admin_headers, email=email, suffix="010")
        u = self._find_user(admin_headers, login)
        r = _api("POST", "/api/v1/auth/forgot-password", json={"login": email})
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert "e-mail de réinitialisation" in r.json().get("message", "")
        self._delete_user(admin_headers, u["user_id"])

    # EMAIL-11: Email is normalized to lowercase when creating
    def test_email11_email_normalized(self, admin_headers):
        email = "MiXeD.CaSe@Example.COM"
        login = self._create_user_with_email(admin_headers, email=email, suffix="011")
        u = self._find_user(admin_headers, login)
        assert u.get("email") == email.lower()
        self._delete_user(admin_headers, u["user_id"])