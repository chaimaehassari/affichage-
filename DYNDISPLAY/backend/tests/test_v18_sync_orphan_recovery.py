"""Robustesse de la synchronisation — famille du bug silencieux.

Couvre les correctifs issus de l'audit du 20/09/2026 :

1. _upsert_media_sync_state : un échec d'INSERT est isolé dans un SAVEPOINT,
   logué (error : post_id, media_id, horodatage, exception), et le reste de la
   transaction reste utilisable (le bug d'origine perdait le
   ``UPDATE posts SET last_sync_at`` => COMPLETED sans last_sync_at).
2. site_service : même remède pour l'ajout de poste à un groupe
   (screen_group_posts), l'application d'une configuration au groupe et la
   création des jobs de sync groupés (failed_post_ids exacts + transaction
   intacte).
3. Jobs orphelins : détection et marquage FAILED par recover_orphan_jobs()
   (délai configurable), log "JOB ORPHELIN" visible, postes en cours ignorés,
   idempotence.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
import requests
from psycopg.rows import dict_row

from tests._test_config import get_test_db_url

BASE_URL = "http://localhost:8000"
DB_URL = get_test_db_url()


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _open():
    return psycopg.connect(DB_URL, row_factory=dict_row)


def _admin_user_id(conn) -> int:
    row = conn.execute(
        "SELECT user_id FROM users WHERE login = %s AND is_active = TRUE ORDER BY user_id LIMIT 1",
        ("admin",),
    ).fetchone()
    assert row, "admin introuvable"
    return row["user_id"]


def _client_id(conn) -> int:
    row = conn.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "SELECT client_id FROM sites WHERE is_active = TRUE ORDER BY client_id LIMIT 1"
    ).fetchone()
    return row["client_id"] if row else 1


def _mk_site(conn, client_id: int) -> int:
    row = conn.execute(
        "INSERT INTO sites (code, name, client_id) VALUES (%s, %s, %s) RETURNING site_id",
        (f"V18_{_uid()}", f"Site V18 {_uid()}", client_id),
    ).fetchone()
    return row["site_id"]


def _mk_post(conn, site_id: int) -> int:
    row = conn.execute(
        "INSERT INTO posts (site_id, code, name) VALUES (%s, %s, %s) RETURNING post_id",
        (site_id, f"V18P_{_uid()}", f"Post V18 {_uid()}"),
    ).fetchone()
    return row["post_id"]


def _mk_group(conn) -> int:
    row = conn.execute(
        "INSERT INTO screen_groups (name) VALUES (%s) RETURNING group_id",
        (f"Groupe V18 {_uid()}",),
    ).fetchone()
    return row["group_id"]


def _cleanup_post(conn, post_id: int) -> None:
    conn.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))


@pytest.mark.v18
class TestSyncSavepointOne:

    def test_upsert_media_sync_state_error_logged_and_transaction_usable(self, caplog):
        with _open() as conn:
            cid = _client_id(conn)
            site = _mk_site(conn, cid)
            post = _mk_post(conn, site)

            from app.services.sync_service import SyncService

            svc = SyncService(conn)
            with caplog.at_level(logging.ERROR, logger="app.services.sync_service"):
                # media_id inexistant => violation FK media_sync_state_media_id_fkey
                svc._upsert_media_sync_state(post, {-1}, "SYNCED")

            errs = [r for r in caplog.records if r.message.startswith("ROLLBACK SAVEPOINT")]
            assert errs, "aucun log de rollback SAVEPOINT émis"
            text = str(errs[0].getMessage())
            assert "media_sync_state_sp" in text
            assert f"post_id={post}" in text
            assert "media_id=-1" in text
            assert "media_sync_state" in text  # la table/contrainte en cause

            # L'environnement est intact après l'échec : on écrit puis on commit.
            marker = f"after-savepoint-{_uid()}"
            conn.execute("UPDATE posts SET name = %s WHERE post_id = %s", (marker, post))
            conn.commit()

            conn2 = _open()
            try:
                name = conn2.execute(
                    "SELECT name FROM posts WHERE post_id = %s", (post,)
                ).fetchone()["name"]
                assert name == marker
            finally:
                conn2.close()

            _cleanup_post(conn, post)
            conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
            conn.commit()


@pytest.mark.v18
class TestSiteServiceSavepoint:

    def test_membership_insert_failure_isolated_and_logged(self, caplog):
        from app.services.site_service import GroupService

        with _open() as conn:
            cid = _client_id(conn)
            site = _mk_site(conn, cid)
            p_ok = _mk_post(conn, site)
            p_ignored = _mk_post(conn, site)
            gid = _mk_group(conn)
            admin = _admin_user_id(conn)
            bogus = 999_999_999  # post_id inexistant => violation FK fk_group_post_post

            svc = GroupService(conn)
            with caplog.at_level(logging.ERROR, logger="app.services.site_service"):
                comp = svc.set_group_membership(gid, [p_ok, bogus], admin, scope=None)

            # Le poste valide est ajouté ; l'inexistant est ignoré sans détruire la suite.
            member_ids = {
                x["post_id"]
                for s in comp["sites"]
                for x in s["posts"]
                if x["in_group"]
            }
            assert p_ok in member_ids
            assert bogus not in member_ids
            assert len(member_ids) == 1

            errs = [r for r in caplog.records if "group_membership_sp" in str(r.getMessage())]
            assert errs, "aucun log de rollback SAVEPOINT group_membership_sp"
            text = str(errs[0].getMessage())
            assert f"group_id={gid}" in text
            assert f"post_id={bogus}" in text
            import re
            assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", text)

            # Transaction exploitable, tout est commitable.
            conn.commit()
            row = conn.execute(
                "SELECT post_id FROM screen_group_posts WHERE group_id = %s", (gid,)
            ).fetchall()
            assert [r["post_id"] for r in row] == [p_ok]

            _cleanup_post(conn, p_ok)
            _cleanup_post(conn, p_ignored)
            conn.execute("DELETE FROM screen_groups WHERE group_id = %s", (gid,))
            conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
            conn.commit()

    def test_apply_config_failure_isolated_rolled_back_and_reported(self, caplog):
        import re as _re

        from types import SimpleNamespace
        from app.services.site_service import GroupService

        with _open() as conn:
            cid = _client_id(conn)
            site = _mk_site(conn, cid)
            p_ok = _mk_post(conn, site)
            p_bad = _mk_post(conn, site)
            gid = _mk_group(conn)
            admin = _admin_user_id(conn)

            conn.execute(
                "INSERT INTO screen_group_posts (group_id, post_id) VALUES (%s, %s), (%s, %s)",
                (gid, p_ok, gid, p_bad),
            )

            config_before = conn.execute(
                "SELECT COUNT(*) AS n FROM post_configurations WHERE post_id = ANY(%s)",
                ([p_ok, p_bad],),
            ).fetchone()["n"]

            payload = SimpleNamespace(
                layout_id=None,
                loop_enabled=True,
                schedule_enabled=False,
                display_enabled=True,
                zones=[{"zone_number": 1, "media_id": -999, "display_order": 1, "duration_seconds": 10}],
                sync=False,
            )
            svc = GroupService(conn)
            with caplog.at_level(logging.ERROR, logger="app.services.site_service"):
                result = svc.apply_configuration_to_group(gid, payload, admin, scope=None)

            assert result["success_count"] == 0
            assert sorted(result["failed_post_ids"]) == sorted([p_ok, p_bad])

            errs = [r for r in caplog.records if "apply_config_sp" in str(r.getMessage())]
            assert len(errs) == 2, "un log par poste en échec attendu"
            for r in errs:
                assert _re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", str(r.getMessage()))

            # Aucune écriture partielle ne doit avoir survécu au SAVEPOINT.
            config_after = conn.execute(
                "SELECT COUNT(*) AS n FROM post_configurations WHERE post_id = ANY(%s)",
                ([p_ok, p_bad],),
            ).fetchone()["n"]
            assert config_after == config_before

            # La transaction reste utilisable : une config valide passe ensuite.
            ok_payload = SimpleNamespace(
                layout_id=None,
                loop_enabled=True,
                schedule_enabled=False,
                display_enabled=True,
                zones=[],
                sync=False,
            )
            ok_result = svc.apply_configuration_to_group(gid, ok_payload, admin, scope=None)
            assert ok_result["success_count"] == 2
            assert ok_result["failed_post_ids"] == []
            conn.commit()

            row = conn.execute(
                "SELECT COUNT(*) AS n FROM post_configurations WHERE post_id = ANY(%s)",
                ([p_ok, p_bad],),
            ).fetchone()["n"]
            assert row == config_before + 2

            _cleanup_post(conn, p_ok)
            _cleanup_post(conn, p_bad)
            conn.execute("DELETE FROM screen_groups WHERE group_id = %s", (gid,))
            conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
            conn.commit()


@pytest.mark.v18
class TestSyncOrphanRecovery:

    def test_orphan_jobs_detected_and_marked_failed(self, caplog):
        from app.services.sync_service import SyncService

        with _open() as conn:
            cid = _client_id(conn)
            site = _mk_site(conn, cid)
            p_orphan = _mk_post(conn, site)
            p_orphan_sched = _mk_post(conn, site)
            p_busy = _mk_post(conn, site)
            p_recent = _mk_post(conn, site)
            admin = _admin_user_id(conn)

            now = datetime.now(timezone.utc)
            old = now - timedelta(hours=2)

            # PENDING orphelin (ancien) — serait détecté.
            j_orphan = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at, started_at) "
                "VALUES (%s, 'PENDING', %s, NULL) RETURNING sync_job_id",
                (p_orphan, old),
            ).fetchone()["sync_job_id"]
            # PENDING orphelin sur un poste qui tourne (concurrent) — à ignorer.
            j_busy = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at, started_at) "
                "VALUES (%s, 'PENDING', %s, NULL) RETURNING sync_job_id",
                (p_busy, old),
            ).fetchone()["sync_job_id"]
            conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at, started_at) "
                "VALUES (%s, 'RUNNING', %s, %s)",
                (p_busy, old, now - timedelta(hours=1)),
            )
            # PENDING récent — à laisser intact.
            j_recent = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at, started_at) "
                "VALUES (%s, 'PENDING', %s, NULL) RETURNING sync_job_id",
                (p_recent, now),
            ).fetchone()["sync_job_id"]
            # SCHEDULED échu depuis longtemps — à marquer FAILED.
            j_sched = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, scheduled_at) "
                "VALUES (%s, 'SCHEDULED', %s) RETURNING sync_job_id",
                (p_orphan_sched, old + timedelta(minutes=10)),
            ).fetchone()["sync_job_id"]

            svc = SyncService(conn)
            with caplog.at_level(logging.WARNING, logger="app.services.sync_service"):
                recovered = svc.recover_orphan_jobs(delay=timedelta(minutes=30))

            # j_orphan (PENDING ancien) et j_sched (échu) récupérés ; les autres non.
            assert recovered == 2
            statuses = {
                r["sync_job_id"]: r["status"]
                for r in conn.execute(
                    "SELECT sync_job_id, status, error_message FROM sync_jobs "
                    "WHERE sync_job_id = ANY(%s)",
                    ([j_orphan, j_recent, j_sched, j_busy],),
                ).fetchall()
            }
            assert statuses[j_orphan] == "FAILED"
            assert statuses[j_sched] == "FAILED"
            assert statuses[j_recent] == "PENDING"
            assert statuses[j_busy] == "PENDING"

            msg = conn.execute(
                "SELECT error_message FROM sync_jobs WHERE sync_job_id = %s", (j_orphan,)
            ).fetchone()["error_message"]
            assert msg.startswith("Job orphelin")

            warns = [r for r in caplog.records if "JOB ORPHELIN" in str(r.getMessage())]
            assert len(warns) == 2, "un log visible par job orphelin attendu"
            joined = str(warns[0].getMessage()) + str(warns[1].getMessage())
            assert f"post_id={p_orphan}" in joined
            assert f"post_id={p_orphan_sched}" in joined

            # Idempotence : un second passage ne change rien.
            again = svc.recover_orphan_jobs(delay=timedelta(minutes=30))
            assert again == 0

            # Nettoyage des job rows restants, puis des entités.
            conn.execute(
                "DELETE FROM sync_jobs WHERE post_id = ANY(%s)",
                ([p_orphan, p_orphan_sched, p_busy, p_recent],),
            )
            _cleanup_post(conn, p_orphan)
            _cleanup_post(conn, p_orphan_sched)
            _cleanup_post(conn, p_busy)
            _cleanup_post(conn, p_recent)
            conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
            conn.commit()


@pytest.mark.v18
class TestApplyConfigFailedListSurfaced:

    def test_failed_post_ids_surfaces_the_group_failures(self, admin_headers):
        r = _api("POST", "/api/v1/sites", headers=admin_headers,
                 json={"code": f"V18_{_uid()}", "name": "Site v18", "is_active": True})
        assert r.status_code == 201, r.text
        site_id = r.json()["site_id"]
        posts = []
        group_id = None
        try:
            for _ in range(2):
                r = _api("POST", "/api/v1/posts", headers=admin_headers,
                         json={"site_id": site_id, "code": f"V18P_{_uid()}", "name": "Post v18",
                               "is_active": True})
                assert r.status_code == 201, r.text
                posts.append(r.json()["post_id"])
            r = _api("POST", "/api/v1/groups", headers=admin_headers,
                     json={"name": f"Groupe V18 {_uid()}", "description": "test", "is_active": True})
            assert r.status_code == 201, r.text
            group_id = r.json()["group_id"]
            r = _api("PUT", f"/api/v1/groups/{group_id}/membership", headers=admin_headers,
                     json={"post_ids": posts})
            assert r.status_code == 200, r.text

            # Média inexistant : chaque poste échoue, la liste des échecs est remontée.
            r = _api("POST", f"/api/v1/groups/{group_id}/apply-configuration",
                     headers=admin_headers,
                     json={
                         "layout_id": None, "loop_enabled": True, "schedule_enabled": False,
                         "display_enabled": True, "sync": False,
                         "zones": [{"zone_number": 1, "media_id": -999, "display_order": 1,
                                    "duration_seconds": 10}],
                     })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success_count"] == 0
            assert sorted(body["failed_post_ids"]) == sorted(posts)
            assert "synced_post_ids" in body

            # La transaction commit bien : le groupe reste cohérent côté API.
            comp = _api("GET", f"/api/v1/groups/{group_id}/composition", headers=admin_headers)
            assert comp.status_code == 200
            assert comp.json()["post_count"] == 2
        finally:
            for pid in posts:
                _api("DELETE", f"/api/v1/posts/{pid}", headers=admin_headers)
            if group_id:
                _api("DELETE", f"/api/v1/groups/{group_id}", headers=admin_headers)
            try:
                _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)
            except requests.RequestException:
                pass