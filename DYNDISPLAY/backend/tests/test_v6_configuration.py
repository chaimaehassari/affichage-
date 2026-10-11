import uuid

import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _create_site(headers, code=None):
    code = code or f"V6_{_uid()}"
    r = _api("POST", "/api/v1/sites", headers=headers, json={
        "code": code, "name": f"Site {code}", "is_active": True,
   "client_code": _client_code(),
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_post(headers, site_id, code=None):
    code = code or f"V6P_{_uid()}"
    r = _api("POST", "/api/v1/posts", headers=headers, json={
        "site_id": site_id, "code": code, "name": f"Post {code}", "is_active": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_layout(headers, name=None):
    name = name or f"Layout V6 {_uid()}"
    r = _api("POST", "/api/v1/layouts", headers=headers, json={
        "name": name, "is_active": True,
        "zones": [
            {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 50, "height": 100, "is_active": True},
            {"zone_number": 2, "position_x": 50, "position_y": 0, "width": 50, "height": 100, "is_active": True},
        ],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _cleanup(headers, site_id, post_id=None):
    if post_id:
        _api("DELETE", f"/api/v1/posts/{post_id}", headers=headers)
    _api("DELETE", f"/api/v1/sites/{site_id}", headers=headers)


def _get_schedule_id(schedule_json):
    return schedule_json.get("schedule_id") or schedule_json.get("id")



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


@pytest.mark.v6
class TestV6Configuration:

    def test_config01_get_post_configuration_no_config(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])

        r = _api("GET", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers)
        assert r.status_code == 200
        config = r.json()
        assert config is not None

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config02_update_post_configuration_with_layout_and_zones(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])
        layout = _create_layout(admin_headers)

        media_r = _api("GET", "/api/v1/media", headers=admin_headers)
        assert media_r.status_code == 200
        media_list = media_r.json()
        media_id = media_list[0]["media_id"] if media_list else None

        payload = {
            "layout_id": layout["layout_id"],
            "loop_enabled": True,
            "schedule_enabled": False,
            "display_enabled": True,
            "zones": [
                {"zone_number": 1, "media_id": media_id},
                {"zone_number": 2, "media_id": None},
            ],
        }
        r = _api("PUT", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers, json=payload)
        assert r.status_code == 200

        r2 = _api("GET", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers)
        assert r2.status_code == 200
        config = r2.json()
        assert config["layout"]["layout_id"] == layout["layout_id"]
        assert config["loop_enabled"] is True
        assert len(config["zones"]) == 2
        assert config["zones"][0]["zone_number"] == 1

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config03_update_zone_media_assignments(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])
        layout = _create_layout(admin_headers)

        _api("PUT", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers, json={"layout_id": layout["layout_id"]})

        media_r = _api("GET", "/api/v1/media", headers=admin_headers)
        media_list = media_r.json()
        media_id = media_list[0]["media_id"] if media_list else None

        payload = [
            {"zone_number": 1, "media_id": media_id},
            {"zone_number": 2, "media_id": None},
        ]
        r = _api("POST", f"/api/v1/posts/{post['post_id']}/zones", headers=admin_headers, json=payload)
        assert r.status_code == 200

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config04_create_schedule(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])

        payload = {
            "name": f"Planning {_uid()}",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "start_time": "08:00:00",
            "end_time": "20:00:00",
            "days_of_week": "1,2,3,4,5",
            "is_active": True,
        }
        r = _api("POST", f"/api/v1/posts/{post['post_id']}/schedules", headers=admin_headers, json=payload)
        assert r.status_code == 201
        body = r.json()
        assert "schedule_id" in body or "id" in body
        assert body["name"] == payload["name"]

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config05_list_schedules_for_post(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])

        _api("POST", f"/api/v1/posts/{post['post_id']}/schedules", headers=admin_headers, json={
            "name": f"Planning {_uid()}",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "start_time": "08:00:00",
            "end_time": "20:00:00",
            "days_of_week": "1,2,3,4,5",
            "is_active": True,
        })

        r = _api("GET", f"/api/v1/posts/{post['post_id']}/schedules", headers=admin_headers)
        assert r.status_code == 200
        schedules = r.json()
        assert len(schedules) > 0

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config06_update_schedule(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])

        create_r = _api("POST", f"/api/v1/posts/{post['post_id']}/schedules", headers=admin_headers, json={
            "name": f"Planning {_uid()}",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "start_time": "08:00:00",
            "end_time": "20:00:00",
            "days_of_week": "1,2,3,4,5",
            "is_active": True,
        })
        schedule_id = _get_schedule_id(create_r.json())

        r = _api("PUT", f"/api/v1/schedules/{schedule_id}", headers=admin_headers, json={"name": f"Updated {_uid()}"})
        assert r.status_code == 200

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config07_delete_schedule(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])

        create_r = _api("POST", f"/api/v1/posts/{post['post_id']}/schedules", headers=admin_headers, json={
            "name": f"Planning {_uid()}",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "start_time": "08:00:00",
            "end_time": "20:00:00",
            "days_of_week": "1,2,3,4,5",
            "is_active": True,
        })
        schedule_id = _get_schedule_id(create_r.json())

        r = _api("DELETE", f"/api/v1/schedules/{schedule_id}", headers=admin_headers)
        assert r.status_code == 200

        r2 = _api("GET", f"/api/v1/posts/{post['post_id']}/schedules", headers=admin_headers)
        assert r2.status_code == 200
        schedules = r2.json()
        schedule_ids = [_get_schedule_id(s) for s in schedules]
        assert schedule_id not in schedule_ids

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config08_toggle_loop_enabled(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])
        layout = _create_layout(admin_headers)

        _api("PUT", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers, json={
            "layout_id": layout["layout_id"], "loop_enabled": True,
        })

        r1 = _api("GET", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers)
        assert r1.json()["loop_enabled"] is True

        _api("PUT", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers, json={
            "layout_id": layout["layout_id"], "loop_enabled": False,
        })

        r2 = _api("GET", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers)
        assert r2.json()["loop_enabled"] is False

        _cleanup(admin_headers, site["site_id"], post["post_id"])

    def test_config09_config_preview_endpoint(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])
        layout = _create_layout(admin_headers)

        media_r = _api("GET", "/api/v1/media", headers=admin_headers)
        media_list = media_r.json()
        media_id = media_list[0]["media_id"] if media_list else None

        _api("PUT", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers, json={
            "layout_id": layout["layout_id"],
            "loop_enabled": True,
            "zones": [
                {"zone_number": 1, "media_id": media_id},
                {"zone_number": 2, "media_id": None},
            ],
        })

        r = _api("GET", f"/api/v1/posts/{post['post_id']}/config-preview", headers=admin_headers)
        assert r.status_code == 200
        preview = r.json()
        assert "layout" in preview or "layout_id" in preview
        assert "zones" in preview
        assert "loop_enabled" in preview

        _cleanup(admin_headers, site["site_id"], post["post_id"])
