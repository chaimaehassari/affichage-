import uuid
import requests

BASE = "http://localhost:8000"


def main():
    with requests.Session() as s:
        r = s.post(f"{BASE}/api/v1/auth/login",
                   json={"login": "admin", "password": "admin123"},
                   headers={"X-Device-Id": "smoke-device"})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        H = {"Authorization": f"Bearer {token}", "X-Device-Id": "smoke-device"}

        # Find an admin (non-superadmin prefered)
        r = s.get(f"{BASE}/api/v1/users", headers=H)
        assert r.status_code == 200, r.text
        users = r.json()["users"]
        admins = [u for u in users if u["profile_name"] == "Administrateur"]
        target = admins[0] if admins else None
        print("admin target:", target["login"] if target else None)

        login = f"smoke_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{BASE}/api/v1/users", headers=H, json={
            "user_code": f"SM{uuid.uuid4().hex[:4].upper()}",
            "login": login,
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "admin_id": target["user_id"] if target else None,
            "is_active": True,
            "zones": [1],
            "permissions": [],
        })
        print("create:", r.status_code, r.text)
        assert r.status_code == 201, r.text
        uid = r.json()["user_id"]

        r = s.get(f"{BASE}/api/v1/users", headers=H)
        u = next((x for x in r.json()["users"] if x["user_id"] == uid), None)
        print("listed:", u)
        assert u is not None
        assert u.get("admin_id") == (target["user_id"] if target else None)
        if target:
            assert u["admin_login"] == target["login"]
            assert u["admin_code"] == target["user_code"]

        # invalid admin_id -> 400
        r = s.post(f"{BASE}/api/v1/users", headers=H, json={
            "user_code": f"SM{uuid.uuid4().hex[:4].upper()}",
            "login": f"smoke2_{uuid.uuid4().hex[:6]}",
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "admin_id": 999999,
            "is_active": True,
            "zones": [],
            "permissions": [],
        })
        print("bad admin_id:", r.status_code, r.text)
        assert r.status_code == 400

        # admin_id pointing to a non-admin profile -> 400
        non_admin = next((x for x in users if x["profile_name"] != "Administrateur"), None)
        if non_admin:
            r = s.post(f"{BASE}/api/v1/users", headers=H, json={
                "user_code": f"SM{uuid.uuid4().hex[:4].upper()}",
                "login": f"smoke3_{uuid.uuid4().hex[:6]}",
                "password": "Test@1234",
                "password_confirm": "Test@1234",
                "profile_id": 2,
                "admin_id": non_admin["user_id"],
                "is_active": True,
                "zones": [],
                "permissions": [],
            })
            print("non-admin target:", r.status_code, r.text)
            assert r.status_code == 400

        r = s.delete(f"{BASE}/api/v1/users/{uid}", headers=H)
        assert r.status_code == 200, r.text
        print("deleted", uid)


if __name__ == "__main__":
    main()
    print("SMOKE OK")