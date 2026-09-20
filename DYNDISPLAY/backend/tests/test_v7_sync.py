import json
import os
import time
import uuid

import psycopg
import pytest
import requests

BASE_URL = "http://localhost:8000"
from tests._test_config import get_test_db_url
DB_URL = get_test_db_url()

SFTP_PATH = "C:\\DYNDISPLAY-SFTP"
POST_ID = 7


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_sync(headers, post_id=POST_ID):
    """Start a sync and return (status_code, json_body)."""
    r = _api("POST", f"/api/v1/posts/{post_id}/sync", headers=headers)
    return r.status_code, r.json() if r.content else {}


def _wait_for_completion(headers, job_id, timeout=15, interval=0.5):
    """Poll GET /sync-jobs/{job_id} until status is terminal or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _api("GET", f"/api/v1/sync-jobs/{job_id}", headers=headers)
        if r.status_code == 200:
            body = r.json()
            if body.get("status") in ("COMPLETED", "FAILED", "ERROR"):
                return body
        time.sleep(interval)
    return None


def _ensure_post_configured(headers, post_id=POST_ID):
    """Ensure post has a layout + zone assignment so sync can succeed."""
    cfg = _api("GET", f"/api/v1/posts/{post_id}/configuration", headers=headers)
    if cfg.status_code == 400:
        return
    if cfg.status_code == 200:
        data = cfg.json()
        if data.get("layout_id"):
            return

    layouts = _api("GET", "/api/v1/layouts", headers=headers).json()
    if not layouts:
        return

    _api("PUT", f"/api/v1/posts/{post_id}/configuration", headers=headers, json={
        "layout_id": layouts[0]["layout_id"],
    })


def _get_post_code(headers, post_id=POST_ID):
    """Return the code field for a post (used as player directory name)."""
    posts = _api("GET", "/api/v1/posts", headers=headers).json()
    for p in posts:
        if p.get("post_id") == post_id:
            return p.get("code")
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.v7
class TestSync01GetSyncStatusNoSync:
    def test_sync_status_returns_200(self, admin_headers):
        r = _api("GET", f"/api/v1/posts/{POST_ID}/sync-status", headers=admin_headers)
        assert r.status_code == 200

    def test_sync_status_may_be_null(self, admin_headers):
        r = _api("GET", f"/api/v1/posts/{POST_ID}/sync-status", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        if body is not None:
            assert "sync_job_id" in body
            assert "status" in body


@pytest.mark.v7
class TestSync02StartSync:
    def test_start_sync_returns_pending(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        assert "sync_job_id" in body
        assert body["status"] == "PENDING"
        job_id = body["sync_job_id"]

        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None, "Sync did not complete within 15 seconds"
        assert result["status"] == "COMPLETED"
        assert result["progress_percent"] == 100


@pytest.mark.v7
class TestSync03GetSyncJobDetail:
    def test_sync_job_detail_has_items(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]

        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None, "Sync did not complete within 15 seconds"

        r = _api("GET", f"/api/v1/sync-jobs/{job_id}", headers=admin_headers)
        assert r.status_code == 200
        detail = r.json()
        assert "items" in detail
        assert len(detail["items"]) >= 1

        item_types = [item["item_type"] for item in detail["items"]]
        assert "CONFIG" in item_types


@pytest.mark.v7
class TestSync04VerifySFTPFiles:
    def test_config_json_exists(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]
        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None

        post_code = _get_post_code(admin_headers)
        config_path = os.path.join(SFTP_PATH, "players", post_code, "config.json")
        assert os.path.exists(config_path), f"config.json not found at {config_path}"
        assert os.path.getsize(config_path) > 0

    def test_media_directory_exists(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]
        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None

        post_code = _get_post_code(admin_headers)
        media_dir = os.path.join(SFTP_PATH, "players", post_code, "media")
        assert os.path.isdir(media_dir), f"media dir not found at {media_dir}"


@pytest.mark.v7
class TestSync05VerifyConfigJsonContent:
    def test_config_json_has_required_keys(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]
        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None

        post_code = _get_post_code(admin_headers)
        config_path = os.path.join(SFTP_PATH, "players", post_code, "config.json")
        assert os.path.exists(config_path)

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        assert "post_id" in config
        assert "code" in config
        assert "layout" in config
        assert "zones" in config
        assert isinstance(config["zones"], list)


@pytest.mark.v7
class TestSync06DuplicateSyncPrevention:
    def test_duplicate_sync_returns_409(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]

        status2, _ = _start_sync(admin_headers)
        if status2 == 200:
            _wait_for_completion(admin_headers, body["sync_job_id"], timeout=15)
            pytest.skip("Sync completed before duplicate could be detected")

        assert status2 == 409
        _wait_for_completion(admin_headers, job_id, timeout=15)


@pytest.mark.v7
class TestSync07ConfigPreview:
    def test_config_preview_returns_200(self, admin_headers):
        r = _api("GET", f"/api/v1/posts/{POST_ID}/config-preview", headers=admin_headers)
        assert r.status_code == 200

    def test_config_preview_has_layout_and_zones(self, admin_headers):
        _ensure_post_configured(admin_headers)
        r = _api("GET", f"/api/v1/posts/{POST_ID}/config-preview", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "layout" in body
        assert "zones" in body


@pytest.mark.v7
class TestSync08SyncNonExistentPost:
    def test_sync_nonexistent_post_returns_404(self, admin_headers):
        r = _api("POST", "/api/v1/posts/99999/sync", headers=admin_headers)
        assert r.status_code == 404


@pytest.mark.v7
class TestSync09GetNonExistentSyncJob:
    def test_get_nonexistent_job_returns_404(self, admin_headers):
        r = _api("GET", "/api/v1/sync-jobs/99999", headers=admin_headers)
        assert r.status_code == 404


@pytest.mark.v7
class TestSync10VerifyDBRecords:
    def test_sync_job_record_exists_in_db(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]
        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None

        with psycopg.connect(DB_URL) as conn:
            job = conn.execute(
                "SELECT status FROM sync_jobs WHERE sync_job_id = %s",
                (job_id,),
            ).fetchone()
            assert job is not None
            assert job[0] == "COMPLETED"

            items = conn.execute(
                "SELECT item_type FROM sync_items WHERE sync_job_id = %s",
                (job_id,),
            ).fetchall()
            assert len(items) >= 1

            item_types = {item[0] for item in items}
            assert "CONFIG" in item_types


@pytest.mark.v7
class TestSync11MultiplePostsSync:
    def test_sync_status_returns_latest_job(self, admin_headers):
        _ensure_post_configured(admin_headers)
        status, body = _start_sync(admin_headers)
        assert status == 200
        job_id = body["sync_job_id"]
        result = _wait_for_completion(admin_headers, job_id, timeout=15)
        assert result is not None

        r = _api("GET", f"/api/v1/posts/{POST_ID}/sync-status", headers=admin_headers)
        assert r.status_code == 200
        latest = r.json()
        assert latest is not None
        assert latest["sync_job_id"] == job_id
        assert latest["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Helpers for auto-scheduled (deferred) sync tests
# ---------------------------------------------------------------------------

def _make_site_post():
    """Create a dedicated site + post via a committed connection."""
    with psycopg.connect(DB_URL) as conn:
        site = conn.execute(
            "INSERT INTO sites (code, name, is_active, client_id) VALUES (%s, %s, TRUE, (SELECT id FROM clients ORDER BY id LIMIT 1)) RETURNING site_id",
            (f"AS{uuid.uuid4().hex[:6].upper()}", "AutoSync Site"),
        ).fetchone()
        site_id = site[0]
        post = conn.execute(
            """
            INSERT INTO posts (site_id, code, name, is_active)
            VALUES (%s, %s, %s, TRUE) RETURNING post_id
            """,
            (site_id, f"AS{uuid.uuid4().hex[:6].upper()}", "AutoSync Post"),
        ).fetchone()
        conn.commit()
        return site_id, int(post[0])


def _destroy_site_post(site_id, post_id):
    with psycopg.connect(DB_URL) as conn:
        conn.execute("DELETE FROM sync_jobs WHERE post_id = %s", (post_id,))
        conn.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
        conn.execute("DELETE FROM sites WHERE site_id = %s", (site_id,))
        conn.commit()


@pytest.mark.v7
class TestSync12AutoScheduledSync:
    """CPS: les réglages sync_auto_* (mode Différé) alimentent le scheduler :
    un job est planifié pour chaque poste actif, au plus un par jour."""

    def test_auto_scheduled_job_created_and_idempotent(self, admin_headers):
        from datetime import datetime, timezone as tz_utc

        site_id, post_id = _make_site_post()
        test_start = datetime.now(tz_utc.utc)
        try:
            r = _api("PUT", "/api/v1/settings", headers=admin_headers, json={
                "sync_auto_enabled": True,
                "sync_auto_schedule": "deferred",
                "sync_auto_time": "00:00",
                "sync_auto_profile_id": "",
            })
            assert r.status_code == 200, r.text

            # Le scheduler (toutes les ~15 s) doit créer le job automatiquement.
            deadline = time.time() + 35
            found = False
            while time.time() < deadline:
                with psycopg.connect(DB_URL) as conn:
                    row = conn.execute(
                        "SELECT sync_job_id, status FROM sync_jobs WHERE post_id = %s AND created_at >= %s LIMIT 1",
                        (post_id, test_start),
                    ).fetchone()
                if row:
                    found = True
                    break
                time.sleep(0.5)
            assert found, "Le scheduler automatique n'a créé aucun job pour le poste"

            # Idempotence : un cycle scheduler supplémentaire ne doit pas
            # dupliquer le job du jour.
            time.sleep(17)
            with psycopg.connect(DB_URL) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM sync_jobs WHERE post_id = %s AND created_at >= %s",
                    (post_id, test_start),
                ).fetchone()
            assert count[0] == 1, f"Expected 1 job, got {count[0]}"
        finally:
            _api("PUT", "/api/v1/settings", headers=admin_headers, json={
                "sync_auto_enabled": False,
                "sync_auto_schedule": "realtime",
                "sync_auto_time": "02:00",
                "sync_auto_profile_id": "",
            })
            # Nettoyage des jobs créés pendant le test (tous postes confondus)
            # pour ne pas interférer avec les autres tests.
            with psycopg.connect(DB_URL) as conn:
                conn.execute("DELETE FROM sync_jobs WHERE created_at >= %s", (test_start,))
                conn.commit()
            _destroy_site_post(site_id, post_id)


@pytest.mark.v7
class TestSync13ScheduleInLocalTime:
    """CPS: scheduled_at saisi côté UI (heure locale, sans fuseau) est
    interprété dans le fuseau de l'application puis stocké en UTC."""

    def test_future_scheduled_at_stored_as_utc(self, admin_headers):
        from datetime import datetime, timedelta, timezone as tz_utc

        site_id, post_id = _make_site_post()
        try:
            local_now = datetime.now().astimezone()
            target_local = local_now + timedelta(minutes=10)
            iso = target_local.strftime("%Y-%m-%dT%H:%M")

            r = _api("POST", f"/api/v1/posts/{post_id}/sync",
                     headers=admin_headers, json={"scheduled_at": iso})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "SCHEDULED"
            assert body["scheduled_at"] is not None

            stored = datetime.fromisoformat(body["scheduled_at"])
            expected = target_local.replace(second=0, microsecond=0).astimezone(tz_utc.utc)
            assert stored == expected
        finally:
            with psycopg.connect(DB_URL) as conn:
                conn.execute(
                    "DELETE FROM sync_jobs WHERE post_id = %s", (post_id,))
                conn.commit()
            _destroy_site_post(site_id, post_id)
