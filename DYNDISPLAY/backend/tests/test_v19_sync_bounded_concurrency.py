"""Concurrence bornée des syncs — saturation PostgreSQL (max_connections).

Couvre le correctif contre l'orage d'auto-sync :

1. L'executor borné (BoundedSyncExecutor) limite le nombre de jobs de sync
   exécutés EN PARALLÈLE ; les jobs au-delà attendent dans la file (ils ne
   sont ni perdus ni échoués immédiatement) — le statut reste
   PENDING/SCHEDULED, aucun nouveau statut inventé.
2. Coordination avec la reprise des orphelins : un job légitimement en file
   (executor non vide) est EXCLU de recover_orphan_jobs() pour ne pas être
   faussement marqué FAILED avant d'avoir eu sa chance.
3. Le pool de connexions dédié « gesto-sync » est dimensionné à
   SYNC_MAX_WORKERS et distinct du pool API « gesto-api » : la limite est
   respectée de bout en bout (threads ET connexions), et l'API web n'est
   jamais privée de ses connexions.
"""

import threading
import time
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from tests._test_config import get_test_db_url

DB_URL = get_test_db_url()


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _open():
    return psycopg.connect(DB_URL, row_factory=dict_row)


@pytest.mark.v19
class TestSyncExecutorBounds:
    """L'executor borne le parallélisme et garde les jobs excédentaires en file."""

    def test_peak_concurrency_never_exceeds_max_workers(self, monkeypatch):
        from app.services import sync_executor as executor_module
        from app.services.sync_executor import BoundedSyncExecutor

        lock = threading.Lock()
        active = 0
        peak = 0
        completed = []

        def stub(post_id, job_id, media_ids=None):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.15)
            with lock:
                active -= 1
                completed.append(job_id)
            return True

        monkeypatch.setattr(executor_module, "run_sync_task", stub)
        ex = BoundedSyncExecutor(max_workers=4)
        try:
            for i in range(16):
                ex.submit(100 + i, 5000 + i)
            # 16 soumis en rafale : seuls 4 tournent, 12 sont en file.
            stats = ex.snapshot()
            assert stats["running"] == 4
            assert stats["queued"] == 12
            assert stats["max_workers"] == 4

            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if len(completed) == 16:
                    break
                time.sleep(0.05)
            assert len(completed) == 16, "aucun job perdu : tous ont fini"
            assert peak == 4, f"pic={peak} > max_workers=4"

            final = ex.snapshot()
            assert final["running"] == 0
            assert final["queued"] == 0
            assert final["submitted_total"] == 16
            assert final["completed"] == 16
            assert final["failed"] == 0
        finally:
            ex.shutdown(wait=True)

    def test_active_job_ids_covers_queued_and_running(self, monkeypatch):
        from app.services import sync_executor as executor_module
        from app.services.sync_executor import BoundedSyncExecutor

        def stub(post_id, job_id, media_ids=None):
            time.sleep(0.2)
            return True

        monkeypatch.setattr(executor_module, "run_sync_task", stub)
        ex = BoundedSyncExecutor(max_workers=2)
        try:
            for i in range(6):
                ex.submit(200 + i, 6000 + i)
            active = ex.active_job_ids()
            assert len(active) == 6, "les 6 jobs soumis (file + en cours) sont actifs"
            assert 6000 in active and 6005 in active
            time.sleep(1.0)
            assert ex.active_job_ids() == set()
        finally:
            ex.shutdown(wait=True)


@pytest.mark.v19
class TestOrphanRecoveryExclusion:
    """Un job en file dans l'executor n'est pas marqué FAILED par la reprise."""

    def test_exclude_job_ids_spares_queued_jobs(self):
        from datetime import datetime, timedelta, timezone

        from app.services.sync_service import SyncService

        with _open() as conn:
            cid = conn.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()["id"]
            site = conn.execute(
                "INSERT INTO sites (code, name, client_id) VALUES (%s, %s, %s) RETURNING site_id",
                (f"V19_{_uid()}", f"Site V19 {_uid()}", cid),
            ).fetchone()["site_id"]
            p1 = conn.execute(
                "INSERT INTO posts (site_id, code, name) VALUES (%s, %s, %s) RETURNING post_id",
                (site, f"V19P_{_uid()}", f"Post V19 {_uid()}"),
            ).fetchone()["post_id"]
            p2 = conn.execute(
                "INSERT INTO posts (site_id, code, name) VALUES (%s, %s, %s) RETURNING post_id",
                (site, f"V19Q_{_uid()}", f"Post V19 {_uid()}"),
            ).fetchone()["post_id"]

            old = datetime.now(timezone.utc) - timedelta(hours=2)
            # j_in_file : "en file" (soumis à l'executor, statut encore PENDING).
            j_in_file = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at) VALUES (%s, 'PENDING', %s) RETURNING sync_job_id",
                (p1, old),
            ).fetchone()["sync_job_id"]
            # j_vraiment_orphelin : jamais soumis, à récupérer.
            j_orphan = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at) VALUES (%s, 'PENDING', %s) RETURNING sync_job_id",
                (p2, old),
            ).fetchone()["sync_job_id"]

            try:
                svc = SyncService(conn)
                recovered = svc.recover_orphan_jobs(
                    delay=timedelta(minutes=30), exclude_job_ids={j_in_file}
                )
                assert recovered == 1
                statuses = {
                    r["sync_job_id"]: r["status"]
                    for r in conn.execute(
                        "SELECT sync_job_id, status FROM sync_jobs WHERE sync_job_id = ANY(%s)",
                        ([j_in_file, j_orphan],),
                    ).fetchall()
                }
                assert statuses[j_in_file] == "PENDING", \
                    "le job en file (exclu) ne doit pas être marqué FAILED"
                assert statuses[j_orphan] == "FAILED"
            finally:
                conn.execute("DELETE FROM sync_jobs WHERE sync_job_id = ANY(%s)", ([j_in_file, j_orphan],))
                conn.execute("DELETE FROM posts WHERE post_id = ANY(%s)", ([p1, p2],))
                conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
                conn.commit()

    def test_recover_orphan_jobs_accepts_zero_delay(self):
        """timedelta(seconds=0) est un délai valide (régressions du `or`)."""
        from datetime import datetime, timedelta, timezone

        from app.services.sync_service import SyncService

        with _open() as conn:
            cid = conn.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()["id"]
            site = conn.execute(
                "INSERT INTO sites (code, name, client_id) VALUES (%s, %s, %s) RETURNING site_id",
                (f"V19Z_{_uid()}", f"Site V19 {_uid()}", cid),
            ).fetchone()["site_id"]
            p = conn.execute(
                "INSERT INTO posts (site_id, code, name) VALUES (%s, %s, %s) RETURNING post_id",
                (site, f"V19P_{_uid()}", f"Post V19 {_uid()}"),
            ).fetchone()["post_id"]
            j = conn.execute(
                "INSERT INTO sync_jobs (post_id, status, created_at) VALUES (%s, 'PENDING', %s) RETURNING sync_job_id",
                (p, datetime.now(timezone.utc)),
            ).fetchone()["sync_job_id"]
            try:
                svc = SyncService(conn)
                # Un délai nul tomberait dans `or ORPHAN_JOB_TIMEOUT` avant la
                # correction ; ici il doit être respecté tel quel.
                recovered = svc.recover_orphan_jobs(delay=timedelta(seconds=0))
                assert recovered == 1
                status = conn.execute(
                    "SELECT status FROM sync_jobs WHERE sync_job_id = %s", (j,)
                ).fetchone()["status"]
                assert status == "FAILED"
            finally:
                conn.execute("DELETE FROM sync_jobs WHERE sync_job_id = %s", (j,))
                conn.execute("DELETE FROM posts WHERE post_id = %s", (p,))
                conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
                conn.commit()


@pytest.mark.v19
class TestJobVisibilityWait:
    """Un job soumis AVANT le commit (route HTTP / apply de groupe) doit être
    attendu par le worker, sinon succès fantôme (PENDING figé)."""

    def test_run_sync_task_waits_for_committed_job(self, monkeypatch):
        from app.services import sync_executor as executor_module
        from app.services.sync_service import SyncService

        calls = []

        def fake_run_sync(self, post_id, job_id, media_ids=None):
            calls.append((post_id, job_id))

        monkeypatch.setattr(SyncService, "run_sync", fake_run_sync)

        with _open() as conn:
            cid = conn.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()["id"]
            site = conn.execute(
                "INSERT INTO sites (code, name, client_id) VALUES (%s, %s, %s) RETURNING site_id",
                (f"V19W_{_uid()}", f"Site V19 {_uid()}", cid),
            ).fetchone()["site_id"]
            p = conn.execute(
                "INSERT INTO posts (site_id, code, name) VALUES (%s, %s, %s) RETURNING post_id",
                (site, f"V19P_{_uid()}", f"Post V19 {_uid()}"),
            ).fetchone()["post_id"]
            # Ligne INSERTÉE mais PAS committée : un worker naïf la lirait
            # None et sortirait sans rien faire (succès fantôme).
            j = conn.execute(
                "INSERT INTO sync_jobs (post_id, status) VALUES (%s, 'PENDING') RETURNING sync_job_id",
                (p,),
            ).fetchone()["sync_job_id"]
            try:
                outcome = {}
                t = threading.Thread(
                    target=lambda: outcome.setdefault("ok", executor_module.run_sync_task(p, j))
                )
                t.start()
                time.sleep(0.3)
                assert calls == [], "le job n'est pas visible : run_sync ne doit pas démarrer"
                conn.commit()  # rend le job visible pour les autres connexions
                t.join(timeout=10)
                assert outcome.get("ok") is True
                assert calls == [(p, j)]
            finally:
                conn.rollback()
                conn.execute("DELETE FROM sync_jobs WHERE sync_job_id = %s", (j,))
                conn.execute("DELETE FROM posts WHERE post_id = %s", (p,))
                conn.execute("DELETE FROM sites WHERE site_id = %s", (site,))
                conn.commit()

    def test_run_sync_task_times_out_when_job_never_appears(self, monkeypatch):
        from app.services import sync_executor as executor_module

        monkeypatch.setattr(executor_module, "JOB_COMMIT_WAIT_SECONDS", 0.2)
        monkeypatch.setattr(executor_module, "JOB_COMMIT_POLL_SECONDS", 0.01)
        assert executor_module.run_sync_task(1, 99999999) is False


@pytest.mark.v19
class TestSyncPoolDedicated:
    """Pool gesto-sync : dédié, dimensionné à SYNC_MAX_WORKERS, distinct de l'API."""

    def test_sync_pool_dimensioned_and_tagged(self):
        from app.core.config import get_settings
        from app.db import database as db

        settings = get_settings()
        assert db.sync_pool is not db.pool
        assert db.sync_pool.max_size == max(int(settings.SYNC_MAX_WORKERS or 8), 1)
        assert db.pool.max_size == 10  # inchangé : le pool API garde sa taille

        with db.get_sync_connection() as conn:
            assert conn.info.parameter_status("application_name") == "gesto-sync"
            assert conn.execute("SELECT 1 AS x").fetchone()["x"] == 1
        with db.get_connection() as conn:
            assert conn.info.parameter_status("application_name") == "gesto-api"