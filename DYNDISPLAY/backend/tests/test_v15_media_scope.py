import io
import struct
import uuid
import zlib

import pytest
import requests

BASE_URL = "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


TEST_PASSWORD = "Test@1234"


def _create_minimal_png():
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc & 0xFFFFFFFF)
    raw = zlib.compress(b'\x00\xff\x00\x00' + uuid.uuid4().bytes)
    idat_crc = zlib.crc32(b'IDAT' + raw)
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc & 0xFFFFFFFF)
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


# list_sites_posts + CRUD sites/posts + menu_media + update_post (batch assign)
CLIENT_PERMISSIONS = [
    {"permission_id": 11, "can_view": True},    # menu_media
    {"permission_id": 14, "can_view": True},    # list_sites_posts
    {"permission_id": 15, "can_create": True, "can_view": True},  # create_site
    {"permission_id": 16, "can_update": True, "can_view": True},  # update_site
    {"permission_id": 17, "can_delete": True, "can_view": True},  # delete_site
    {"permission_id": 18, "can_create": True, "can_view": True},  # create_post
    {"permission_id": 19, "can_update": True, "can_view": True},  # update_post
    {"permission_id": 20, "can_delete": True, "can_view": True},  # delete_post
]


@pytest.mark.v15
class TestMediaScope:

    def _create_client(self, admin_headers):
        user_code = f"MED{_uid()}"
        login = f"climedia_{_uid()}"
        payload = {
            "user_code": user_code,
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "requires_activation": True,
            "zones": [1, 2, 3, 4],
            "permissions": CLIENT_PERMISSIONS,
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code == 201, r.text
        account_code = r.json().get("account_code")
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

    def _client_headers(self, admin_headers):
        c = self._create_client(admin_headers)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        from app.core.license_utils import generate_license
        code = generate_license(c["user_code"], 5, 20)
        r = _api("POST", "/api/v1/auth/activate", json={"code": code}, headers=headers)
        assert r.status_code == 200, r.text
        return {"client": c, "user": u, "headers": headers}

    def _upload_png(self, headers, name):
        return _api("POST", "/api/v1/media/upload", headers=headers,
                    files={"file": (name, io.BytesIO(_create_minimal_png()), "image/png")})

    def _delete_media(self, headers, media_id):
        return _api("DELETE", f"/api/v1/media/{media_id}", headers=headers)

    # MED-01: un client ne voit que ses médias ; les médias globaux/admin lui sont invisibles
    def test_med01_client_sees_only_own_media(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            global_up = self._upload_png(admin_headers, f"global_{_uid()}.png")
            assert global_up.status_code == 201
            global_id = global_up.json()["media_id"]

            up_a = self._upload_png(a["headers"], f"alpha_{_uid()}.png")
            assert up_a.status_code == 201, up_a.text
            media_a = up_a.json()
            assert media_a["client_code"] == a["client"]["user_code"]
            assert "client_code" in media_a

            list_a = _api("GET", "/api/v1/media", headers=a["headers"]).json()
            ids_a = {m["media_id"] for m in list_a}
            assert media_a["media_id"] in ids_a
            assert global_id not in ids_a

            up_b = self._upload_png(b["headers"], f"beta_{_uid()}.png")
            assert up_b.status_code == 201
            list_a2 = _api("GET", "/api/v1/media", headers=a["headers"]).json()
            assert up_b.json()["media_id"] not in {m["media_id"] for m in list_a2}

            r = _api("GET", f"/api/v1/media/{up_b.json()['media_id']}", headers=a["headers"])
            assert r.status_code == 404
            r = _api("GET", f"/api/v1/media/{global_id}", headers=a["headers"])
            assert r.status_code == 404
        finally:
            for c in (a, b):
                self._delete_media(admin_headers, c["user"]["user_id"])
            self._delete_user(admin_headers, a["user"]["user_id"])
            self._delete_user(admin_headers, b["user"]["user_id"])

    # MED-02: l'admin voit tous les médias (ses globaux + ceux des clients)
    def test_med02_admin_sees_all_media(self, admin_headers):
        a = self._client_headers(admin_headers)
        try:
            up_a = self._upload_png(a["headers"], f"alpha_{_uid()}.png")
            assert up_a.status_code == 201
            media_a = up_a.json()
            admin_list = _api("GET", "/api/v1/media", headers=admin_headers).json()
            assert media_a["media_id"] in {m["media_id"] for m in admin_list}
        finally:
            self._delete_user(admin_headers, a["user"]["user_id"])

    # MED-03: un client ne peut pas supprimer le média d'un autre client
    def test_med03_cannot_delete_other_client_media(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            up_b = self._upload_png(b["headers"], f"beta_{_uid()}.png")
            assert up_b.status_code == 201
            media_b = up_b.json()
            r = self._delete_media(a["headers"], media_b["media_id"])
            assert r.status_code == 400
            assert "introuvable" in r.json().get("detail", "").lower()
            still = _api("GET", f"/api/v1/media/{media_b['media_id']}", headers=b["headers"])
            assert still.status_code == 200
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])

    # MED-04: l'affectation en lot refuse un média hors scope (+ ne réutilise jamais le média d'autrui)
    def test_med04_batch_assign_rejects_out_of_scope_media(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            site_a = _api("POST", "/api/v1/sites", json={
                "code": f"SA{_uid()}", "name": "Site A", "address": "",
                "description": "", "is_active": True, "client_code": a["client"]["user_code"],
            }, headers=admin_headers)
            assert site_a.status_code == 201
            post_a = _api("POST", "/api/v1/posts", json={
                "site_id": site_a.json()["site_id"], "code": f"PA{_uid()}", "name": "P",
                "player_type": "Windows", "ip_address": "", "is_active": True,
            }, headers=a["headers"])
            assert post_a.status_code == 201
            post_id = post_a.json()["post_id"]

            up_b = self._upload_png(b["headers"], f"beta_{_uid()}.png")
            media_b = up_b.json()["media_id"]

            r = _api("POST", "/api/v1/posts/batch-assign-media", headers=a["headers"], json={
                "post_ids": [post_id], "media_id": media_b, "zone_number": 1,
            })
            assert r.status_code == 200, r.text
            result = r.json()
            assert result["success_count"] == 0
            assert post_id in result["failed_ids"]
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])