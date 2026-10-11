import uuid

import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


# ── SITE TESTS ──────────────────────────────────────────────────────────────



# --- Client de rattachement des sites -------------------------------------
# Regle metier : « un site appartient toujours a un client precis »
# (SiteService._resolve_client_id). Un site cree sans `client_code` est refuse.
# Ces anciens tests, ecrits avant le chantier multi-clients, creaient leurs
# sites sans client : on y rattache un client jetable, supprime en fin de
# session pour ne pas polluer la table partagee `clients`.
_TEMP_CLIENTS: list[str] = []


def _client_code() -> str:
    import psycopg
    from tests._test_config import get_test_db_url
    code = "TC" + uuid.uuid4().hex[:8].upper()
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 10, 50)",
                (code, f"Test client {code}"),
            )
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.append(code)
    return code


def pytest_sessionfinish(session, exitstatus):
    if not _TEMP_CLIENTS:
        return
    import psycopg
    from tests._test_config import get_test_db_url
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            for code in _TEMP_CLIENTS:
                cur.execute("DELETE FROM clients WHERE code_client = %s", (code,))
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.clear()


@pytest.mark.v3
class TestSites:

    def test_list_sites(self, admin_headers):
        r = _api("GET", "/api/v1/sites", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_create_site(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "TEST_SITE_V3_001", "name": "Test Site V3", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        body = r.json()
        assert "site_id" in body
        assert body["code"] == "TEST_SITE_V3_001"
        _api("DELETE", f"/api/v1/sites/{body['site_id']}", headers=admin_headers)

    def test_create_site_duplicate_code(self, admin_headers):
        r1 = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "DUP_SITE_V3", "name": "Dup Site A", "is_active": True,
   "client_code": _client_code(),
        })
        assert r1.status_code == 201
        id1 = r1.json()["site_id"]

        r2 = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "DUP_SITE_V3", "name": "Dup Site B", "is_active": True,
   "client_code": _client_code(),
        })
        assert r2.status_code == 400
        _api("DELETE", f"/api/v1/sites/{id1}", headers=admin_headers)

    def test_update_site(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "UPD_SITE_V3_ORIG", "name": "Original Name", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        r2 = _api("PUT", f"/api/v1/sites/{site_id}", headers=admin_headers, json={
            "code": "UPD_SITE_V3", "name": "Updated Site", "is_active": True,
        })
        assert r2.status_code == 200

        r3 = _api("GET", f"/api/v1/sites/{site_id}", headers=admin_headers)
        assert r3.status_code == 200
        assert r3.json()["name"] == "Updated Site"
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)

    def test_delete_site_without_posts(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "DEL_SITE_V3", "name": "To Delete", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        r2 = _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)
        assert r2.status_code == 200

        r3 = _api("GET", f"/api/v1/sites/{site_id}", headers=admin_headers)
        assert r3.status_code == 404


# ── POST TESTS ──────────────────────────────────────────────────────────────


@pytest.mark.v3
class TestPosts:

    def test_list_posts(self, admin_headers):
        r = _api("GET", "/api/v1/posts", headers=admin_headers)
        assert r.status_code == 200

    def test_create_post(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "POST_SITE_V3", "name": "Post Site", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        r2 = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site_id, "code": "TEST_POST_V3_001", "name": "Test Post V3",
            "player_type": "Windows", "is_active": True,
        })
        assert r2.status_code == 201
        body = r2.json()
        assert "post_id" in body
        assert body["code"] == "TEST_POST_V3_001"

        _api("DELETE", f"/api/v1/posts/{body['post_id']}", headers=admin_headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)

    def test_create_post_duplicate_code(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "DUP_POST_SITE_V3", "name": "Dup Post Site", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        r2 = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site_id, "code": "DUP_POST_V3", "name": "Post A",
            "player_type": "Windows", "is_active": True,
        })
        assert r2.status_code == 201
        post_id1 = r2.json()["post_id"]

        r3 = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site_id, "code": "DUP_POST_V3", "name": "Post B",
            "player_type": "Windows", "is_active": True,
        })
        assert r3.status_code == 400

        _api("DELETE", f"/api/v1/posts/{post_id1}", headers=admin_headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)

    def test_update_post(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "UPD_POST_SITE_V3", "name": "Upd Post Site", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        r2 = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site_id, "code": "UPD_POST_V3", "name": "Original Post",
            "player_type": "Windows", "is_active": True,
        })
        assert r2.status_code == 201
        post_id = r2.json()["post_id"]

        r3 = _api("PUT", f"/api/v1/posts/{post_id}", headers=admin_headers, json={
            "site_id": site_id, "code": "UPD_POST_V3", "name": "Updated Post",
            "player_type": "Windows", "is_active": True,
        })
        assert r3.status_code == 200

        r4 = _api("GET", f"/api/v1/posts/{post_id}", headers=admin_headers)
        assert r4.status_code == 200
        assert r4.json()["name"] == "Updated Post"

        _api("DELETE", f"/api/v1/posts/{post_id}", headers=admin_headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)

    def test_delete_post(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "DEL_POST_SITE_V3", "name": "Del Post Site", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        r2 = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site_id, "code": "DEL_POST_V3", "name": "To Delete Post",
            "player_type": "Windows", "is_active": True,
        })
        assert r2.status_code == 201
        post_id = r2.json()["post_id"]

        r3 = _api("DELETE", f"/api/v1/posts/{post_id}", headers=admin_headers)
        assert r3.status_code == 200

        r4 = _api("GET", f"/api/v1/posts/{post_id}", headers=admin_headers)
        assert r4.status_code == 404

        _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)


# ── BATCH TESTS ─────────────────────────────────────────────────────────────


@pytest.mark.v3
class TestBatchAssign:

    def test_batch_assign_media_to_posts(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": "BATCH_SITE_V3", "name": "Batch Site", "is_active": True,
   "client_code": _client_code(),
        })
        assert r.status_code == 201
        site_id = r.json()["site_id"]

        post_ids = []
        for i in range(1, 3):
            rp = _api("POST", "/api/v1/posts", headers=admin_headers, json={
                "site_id": site_id, "code": f"BATCH_POST_V3_{i:03d}",
                "name": f"Batch Post {i}", "player_type": "Windows", "is_active": True,
            })
            assert rp.status_code == 201
            post_ids.append(rp.json()["post_id"])

        rm = _api("GET", "/api/v1/media", headers=admin_headers)
        assert rm.status_code == 200
        media_list = rm.json()
        assert len(media_list) > 0, "Need at least one media item to test batch assign"
        media_id = media_list[0]["media_id"]

        rba = _api("POST", "/api/v1/posts/batch-assign-media", headers=admin_headers, json={
            "post_ids": post_ids, "media_id": media_id, "zone_number": 1,
        })
        assert rba.status_code == 200
        body = rba.json()
        assert body["success_count"] == 2

        for pid in post_ids:
            _api("DELETE", f"/api/v1/posts/{pid}", headers=admin_headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)

    def test_batch_assign_empty_posts(self, admin_headers):
        r = _api("POST", "/api/v1/posts/batch-assign-media", headers=admin_headers, json={
            "post_ids": [], "media_id": 1, "zone_number": 1,
        })
        assert r.status_code in (200, 400)
