import json
import os
import time
import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"

SFTP_BASE = r"C:\DYNDISPLAY-SFTP\players"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _unique(suffix=""):
    return uuid.uuid4().hex[:8].upper() + suffix


@pytest.mark.e2e
class TestE2E01CompleteAdminWorkflow:

    def test_complete_admin_workflow(self, admin_headers):
        headers = admin_headers

        # Step 2 - Create site
        e2e_site_code = "E2E_" + _unique("S")
        e2e_post_code = "E2E_" + _unique("P")
        resp = _api("POST", "/api/v1/sites", headers=headers, json={
            "code": e2e_site_code,
            "name": "E2E Site 001",
            "address": "123 Test Street",
            "description": "E2E test site",
        })
        assert resp.status_code == 201, resp.text
        site_id = resp.json()["site_id"]

        # Step 3 - Create post
        resp = _api("POST", "/api/v1/posts", headers=headers, json={
            "site_id": site_id,
            "code": e2e_post_code,
            "name": "E2E Post 001",
            "player_type": "android",
        })
        assert resp.status_code == 201, resp.text
        post_id = resp.json()["post_id"]

        # Step 4 - Create layout with 2 active zones
        resp = _api("POST", "/api/v1/layouts", headers=headers, json={
            "name": f"E2E Layout {_unique()}",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 50, "height": 100, "is_active": True},
                {"zone_number": 2, "position_x": 50, "position_y": 0, "width": 50, "height": 100, "is_active": True},
            ],
        })
        assert resp.status_code == 201, resp.text
        layout_id = resp.json()["layout_id"]

        # Step 5 - Get a media_id from the library
        resp = _api("GET", "/api/v1/media", headers=headers)
        assert resp.status_code == 200
        media_list = resp.json()
        media_id = media_list[0]["media_id"] if media_list else None

        # Step 6 - Configure the post
        zones = [{"zone_number": 1}, {"zone_number": 2}]
        if media_id:
            zones[0]["media_id"] = media_id
        resp = _api("PUT", f"/api/v1/posts/{post_id}/configuration", headers=headers, json={
            "layout_id": layout_id,
            "loop_enabled": True,
            "schedule_enabled": True,
            "display_enabled": True,
            "zones": zones,
        })
        assert resp.status_code == 200, resp.text

        # Step 7 - Create a schedule
        resp = _api("POST", f"/api/v1/posts/{post_id}/schedules", headers=headers, json={
            "name": "E2E Schedule",
            "days_of_week": "1,2,3,4,5",
            "is_active": True,
        })
        assert resp.status_code == 201, resp.text
        schedule_id = resp.json()["schedule_id"]

        # Step 8 - Verify configuration
        resp = _api("GET", f"/api/v1/posts/{post_id}/configuration", headers=headers)
        assert resp.status_code == 200
        config = resp.json()
        assert config["layout"] is not None
        assert config["layout"]["layout_id"] == layout_id
        assert len(config["zones"]) == 2
        assert len(config["schedules"]) >= 1
        assert any(s["schedule_id"] == schedule_id for s in config["schedules"])

        # Step 9 - Sync the post
        resp = _api("POST", f"/api/v1/posts/{post_id}/sync", headers=headers)
        assert resp.status_code == 200, resp.text
        sync_job_id = resp.json()["sync_job_id"]

        deadline = time.time() + 15
        final_status = None
        while time.time() < deadline:
            resp = _api("GET", f"/api/v1/sync-jobs/{sync_job_id}", headers=headers)
            assert resp.status_code == 200
            final_status = resp.json()
            if final_status["status"] == "COMPLETED":
                break
            time.sleep(1)

        assert final_status is not None
        assert final_status["status"] == "COMPLETED", (
            f"Sync did not complete: {final_status['status']} - {final_status.get('error_message')}"
        )

        # Step 10 - Verify SFTP files
        config_path = os.path.join(SFTP_BASE, e2e_post_code, "config.json")
        assert os.path.exists(config_path), f"config.json not found at {config_path}"
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)

        # Step 11 - Cleanup
        _api("DELETE", f"/api/v1/schedules/{schedule_id}", headers=headers)
        _api("DELETE", f"/api/v1/posts/{post_id}", headers=headers)
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=headers)


@pytest.mark.e2e
class TestE2E02MultiSiteMultiPost:

    def test_multi_post_configuration_workflow(self, admin_headers):
        headers = admin_headers

        # Step 2 - Create site
        e2e_multi_site_code = "E2E_" + _unique("MS")
        resp = _api("POST", "/api/v1/sites", headers=headers, json={
            "code": e2e_multi_site_code,
            "name": "E2E Multi-Site",
        })
        assert resp.status_code == 201, resp.text
        site_id = resp.json()["site_id"]

        # Step 3 - Create 3 posts
        post_ids = []
        post_codes = []
        for i in range(1, 4):
            code = f"E2EM_{_unique(str(i))}"
            post_codes.append(code)
            resp = _api("POST", "/api/v1/posts", headers=headers, json={
                "site_id": site_id,
                "code": code,
                "name": f"E2E Multi Post {i}",
            })
            assert resp.status_code == 201, resp.text
            post_ids.append(resp.json()["post_id"])
        assert len(post_ids) == 3

        # Step 4 - Create layout
        resp = _api("POST", "/api/v1/layouts", headers=headers, json={
            "name": f"E2E Multi Layout {_unique()}",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 100, "is_active": True},
            ],
        })
        assert resp.status_code == 201, resp.text
        layout_id = resp.json()["layout_id"]

        # Step 5 - Configure all 3 posts
        for pid in post_ids:
            resp = _api("PUT", f"/api/v1/posts/{pid}/configuration", headers=headers, json={
                "layout_id": layout_id,
                "loop_enabled": True,
                "display_enabled": True,
                "zones": [{"zone_number": 1}],
            })
            assert resp.status_code == 200, resp.text

        # Step 6 - Batch assign media
        resp = _api("GET", "/api/v1/media", headers=headers)
        assert resp.status_code == 200
        media_list = resp.json()
        if media_list:
            media_id = media_list[0]["media_id"]
            resp = _api("POST", "/api/v1/posts/batch-assign-media", headers=headers, json={
                "post_ids": post_ids, "media_id": media_id, "zone_number": 1,
            })
            assert resp.status_code == 200, resp.text
            result = resp.json()
            assert result["success_count"] == 3
            assert result["failed_ids"] == []

        # Step 7 - Sync all 3 posts
        sync_job_ids = []
        for pid in post_ids:
            resp = _api("POST", f"/api/v1/posts/{pid}/sync", headers=headers)
            assert resp.status_code == 200, resp.text
            sync_job_ids.append(resp.json()["sync_job_id"])

        deadline = time.time() + 15
        while time.time() < deadline:
            all_done = True
            for jid in sync_job_ids:
                resp = _api("GET", f"/api/v1/sync-jobs/{jid}", headers=headers)
                assert resp.status_code == 200
                if resp.json()["status"] not in ("COMPLETED", "FAILED"):
                    all_done = False
                    break
            if all_done:
                break
            time.sleep(1)

        # Step 8 - Verify SFTP files
        for i, pid in enumerate(post_ids, 1):
            post_code = f"E2E_MULTI_POST_{i:03d}"
            config_path = os.path.join(SFTP_BASE, post_code, "config.json")
            assert os.path.exists(config_path), f"config.json not found at {config_path}"
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict)

        # Step 9 - Cleanup
        for pid in post_ids:
            _api("DELETE", f"/api/v1/posts/{pid}", headers=headers)
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=headers)


@pytest.mark.e2e
class TestE2E03MediaUploadToConfiguration:

    def test_media_upload_to_configuration_flow(self, admin_headers):
        headers = admin_headers

        # Step 2 - Upload a test image (unique content to avoid hash collision)
        import struct, zlib
        pixel_data = bytes([hash(uuid.uuid4()) % 256, 0, 0])
        raw_row = b'\x00' + pixel_data
        compressed = zlib.compress(raw_row)
        ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr)
        idat_crc = zlib.crc32(b'IDAT' + compressed)
        iend_crc = zlib.crc32(b'IEND')
        tiny_png = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack('>I', 13) + b'IHDR' + ihdr + struct.pack('>I', ihdr_crc & 0xFFFFFFFF)
            + struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc & 0xFFFFFFFF)
            + struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc & 0xFFFFFFFF)
        )
        e2e_media_name = f"e2e_{_unique()}.png"
        resp = _api("POST", "/api/v1/media/upload", headers=headers,
                     files={"file": (e2e_media_name, tiny_png, "image/png")})
        assert resp.status_code == 201, resp.text
        uploaded_media = resp.json()
        media_id = uploaded_media["media_id"]
        assert uploaded_media["name"] == e2e_media_name
        assert uploaded_media["media_type"] == "IMAGE"

        # Step 3 - Create site + post + layout
        e2e_media_site_code = "E2E_" + _unique("MS")
        e2e_media_post_code = "E2E_" + _unique("MP")
        resp = _api("POST", "/api/v1/sites", headers=headers, json={
            "code": e2e_media_site_code, "name": "E2E Media Site",
        })
        assert resp.status_code == 201, resp.text
        site_id = resp.json()["site_id"]

        resp = _api("POST", "/api/v1/posts", headers=headers, json={
            "site_id": site_id, "code": e2e_media_post_code, "name": "E2E Media Post",
        })
        assert resp.status_code == 201, resp.text
        post_id = resp.json()["post_id"]

        resp = _api("POST", "/api/v1/layouts", headers=headers, json={
            "name": f"E2E Media Layout {_unique()}",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 100, "is_active": True},
            ],
        })
        assert resp.status_code == 201, resp.text
        layout_id = resp.json()["layout_id"]

        # Step 4 - Configure post
        resp = _api("PUT", f"/api/v1/posts/{post_id}/configuration", headers=headers, json={
            "layout_id": layout_id,
            "zones": [{"zone_number": 1, "media_id": media_id}],
        })
        assert resp.status_code == 200, resp.text

        # Step 5 - Verify config
        resp = _api("GET", f"/api/v1/posts/{post_id}/configuration", headers=headers)
        assert resp.status_code == 200
        config = resp.json()
        assert config["layout"] is not None
        assert config["layout"]["layout_id"] == layout_id
        zone = next((z for z in config["zones"] if z.get("zone_number") == 1), None)
        assert zone is not None
        zone_media_id = zone.get("media_id") or (zone.get("media") or {}).get("media_id")
        assert zone_media_id == media_id

        # Step 6 - Cleanup
        _api("DELETE", f"/api/v1/posts/{post_id}", headers=headers)
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=headers)
        _api("DELETE", f"/api/v1/sites/{site_id}", headers=headers)
        _api("DELETE", f"/api/v1/media/{media_id}", headers=headers)
