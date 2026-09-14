import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _create_test_user(headers, suffix="001"):
    login = f"pytest_{_uid()}_{suffix}"
    client_code = f"TC{_uid()}"
    payload = {
        "user_code": client_code,
        "login": login,
        "password": "Test@1234",
        "password_confirm": "Test@1234",
        "profile_id": 2,
        "is_active": True,
        "zones": [1, 2],
        "permissions": [],
    }
    r = _api("POST", "/api/v1/users", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    r_list = _api("GET", "/api/v1/users", headers=headers)
    for u in r_list.json().get("users", []):
        if u["login"] == login:
            u["_client_code"] = client_code
            return u
    raise AssertionError(f"User {login} not found after creation")


def _find_user_by_login(headers, login):
    r = _api("GET", "/api/v1/users", headers=headers)
    for u in r.json().get("users", []):
        if u["login"] == login:
            return u
    return None


def _delete_user(headers, user_id):
    _api("DELETE", f"/api/v1/users/{user_id}", headers=headers)


@pytest.mark.v2
class TestUsers:

    def test_list_users(self, admin_headers):
        r = _api("GET", "/api/v1/users", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] > 0

    def test_create_new_user(self, admin_headers):
        unique_login = f"newuser_{_uid()}"
        payload = {
            "login": unique_login,
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "is_active": True,
            "zones": [1, 2],
            "permissions": [],
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code == 201
        user = _find_user_by_login(admin_headers, unique_login)
        user_id = user["user_id"]

        r2 = _api("GET", "/api/v1/users", headers=admin_headers)
        assert r2.status_code == 200
        logins = [u["login"] for u in r2.json()["users"]]
        assert unique_login in logins

        _delete_user(admin_headers, user_id)

    def test_create_duplicate_login(self, admin_headers):
        dup_login = f"dup_{_uid()}"
        payload = {
            "login": dup_login,
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "is_active": True,
            "zones": [1],
            "permissions": [],
        }
        r1 = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r1.status_code == 201
        user = _find_user_by_login(admin_headers, dup_login)
        user_id = user["user_id"]

        r2 = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r2.status_code == 400

        _delete_user(admin_headers, user_id)

    def test_get_user_detail(self, admin_headers):
        created = _create_test_user(admin_headers, "004")
        user_id = created["user_id"]

        r = _api("GET", f"/api/v1/users/{user_id}", headers=admin_headers)
        assert r.status_code == 200
        detail = r.json()
        assert "zones" in detail
        assert "permissions" in detail

        _delete_user(admin_headers, user_id)

    def test_update_user(self, admin_headers):
        created = _create_test_user(admin_headers, "005")
        user_id = created["user_id"]

        r = _api("PUT", f"/api/v1/users/{user_id}", headers=admin_headers, json={
            "login": created["login"],
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "is_active": True,
            "zones": [3, 4, 5],
            "permissions": [],
        })
        assert r.status_code == 200

        r2 = _api("GET", f"/api/v1/users/{user_id}", headers=admin_headers)
        assert r2.status_code == 200
        zones = r2.json()["zones"]
        zone_numbers = [z["zone_number"] if isinstance(z, dict) else z for z in zones]
        assert zone_numbers == [3, 4, 5]

        _delete_user(admin_headers, user_id)

    def test_delete_user(self, admin_headers):
        created = _create_test_user(admin_headers, "006")
        user_id = created["user_id"]

        r = _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)
        assert r.status_code == 200

        r2 = _api("GET", "/api/v1/users", headers=admin_headers)
        ids = [u.get("id") or u.get("user_id") for u in r2.json()["users"]]
        assert user_id not in ids

    def test_cannot_delete_self(self, admin_headers):
        me = _api("GET", "/api/v1/auth/me", headers=admin_headers)
        assert me.status_code == 200
        admin_id = me.json().get("user_id")

        r = _api("DELETE", f"/api/v1/users/{admin_id}", headers=admin_headers)
        assert r.status_code == 400

    def test_get_profiles(self, admin_headers):
        r = _api("GET", "/api/v1/users/profiles", headers=admin_headers)
        assert r.status_code == 200
        profiles = r.json()
        if isinstance(profiles, dict):
            profiles = profiles.get("profiles", [])
        assert len(profiles) > 0

    def test_get_permissions(self, admin_headers):
        r = _api("GET", "/api/v1/users/permissions", headers=admin_headers)
        assert r.status_code == 200
        permissions = r.json()
        if isinstance(permissions, dict):
            permissions = permissions.get("permissions", [])
        assert len(permissions) > 0

    def test_create_user_invalid_password(self, admin_headers):
        payload = {
            "login": f"shortpwd_{_uid()}",
            "password": "ab",
            "password_confirm": "ab",
            "profile_id": 2,
            "is_active": True,
            "zones": [],
            "permissions": [],
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code in (400, 422)

    def test_create_user_password_mismatch(self, admin_headers):
        payload = {
            "login": f"mismatch_{_uid()}",
            "password": "Test@1234",
            "password_confirm": "Different@1",
            "profile_id": 2,
            "is_active": True,
            "zones": [],
            "permissions": [],
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code in (400, 422)

    def test_admin_reset_password(self, admin_headers):
        created = _create_test_user(admin_headers, "012")
        user_id = created["user_id"]
        user_login = created["login"]

        new_password = "NewP@ssw0rd!"
        r = _api("POST", f"/api/v1/users/{user_id}/reset-password", headers=admin_headers, json={
            "new_password": new_password, "password_confirm": new_password,
        })
        assert r.status_code == 200

        r2 = _api("POST", "/api/v1/auth/login", json={"login": user_login, "password": new_password, "client_code": created["_client_code"]})
        assert r2.status_code == 200
        assert "access_token" in r2.json()

        _delete_user(admin_headers, user_id)
