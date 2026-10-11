import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from app.db.database import get_db, get_sync_connection
from app.dependencies.auth import require_permission
from app.schemas.sync import SyncJobOut, SyncJobCreate
from app.services.sync_service import SyncService
from app.services.scope import (
    assert_group_access,
    assert_media_in_scope,
    assert_post_scope,
    client_scope,
    scoped_post_ids,
)
from app.services.sync_executor import sync_executor
from app.core.times import to_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Sync"])


def _job_out(job: dict, items: list[dict]) -> SyncJobOut:
    return SyncJobOut(
        sync_job_id=job["sync_job_id"],
        post_id=job["post_id"],
        status=job["status"],
        progress_percent=job["progress_percent"],
        transfer_speed=job["transfer_speed"],
        estimated_remaining_seconds=job["estimated_remaining_seconds"],
        started_at=job["started_at"].isoformat() if job["started_at"] else None,
        completed_at=job["completed_at"].isoformat() if job["completed_at"] else None,
        error_message=job["error_message"],
        created_at=job["created_at"].isoformat() if job["created_at"] else None,
        scheduled_at=job["scheduled_at"].isoformat() if job["scheduled_at"] else None,
        items=items,
    )


def _job_items(db: Connection, job_id: int) -> list[dict]:
    rows = db.execute(
        """
        SELECT sync_item_id, media_id, item_type, item_path, status, progress_percent
        FROM sync_items
        WHERE sync_job_id = %s
        """,
        (job_id,),
    ).fetchall()
    return [
        {
            "sync_item_id": item["sync_item_id"],
            "media_id": item["media_id"],
            "item_type": item["item_type"],
            "item_path": item["item_path"],
            "status": item["status"],
            "progress_percent": item["progress_percent"],
        }
        for item in rows
    ]


@router.post("/posts/{post_id}/sync", response_model=SyncJobOut)
def start_sync(
    post_id: int,
    payload: SyncJobCreate | None = None,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)

    assert_post_scope(db, current_user, post_id)

    post = db.execute(
        "SELECT post_id FROM posts WHERE post_id = %s",
        (post_id,),
    ).fetchone()
    if not post:
        raise HTTPException(status_code=404, detail="Poste introuvable.")

    running = service.check_running_sync(post_id)
    if running:
        raise HTTPException(status_code=409, detail="Une synchronisation est déjà en cours pour ce poste.")

    scheduled_at = None
    if payload and payload.scheduled_at:
        raw = payload.scheduled_at.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="Format d'horaire invalide.")
        # Un horaire saisi côté UI (sans fuseau) est interprété dans le fuseau
        # de l'application, puis normalisé en UTC avant stockage (TIMESTAMPTZ).
        scheduled_at = to_utc(parsed)

    job = service.create_job(post_id, scheduled_at)
    job_id = job["sync_job_id"]

    # Le commit DOIT précéder la soumission à l'executor : le get_db ne commit
    # qu'en fin de requête, or le worker lit le job sur SA connexion (pool
    # gesto-sync) — un INSERT non committé est invisible (READ COMMITTED) et
    # run_sync sortirait avec « Job not found » (succès fantôme, PENDING figé).
    db.commit()

    if scheduled_at is None:
        sync_executor.submit(post_id, job_id)

    return _job_out(job, [])


@router.get("/sync/load")
def get_sync_load(
    current_user=Depends(require_permission("menu_sync")),
):
    """État de la file de sync : workers occupés, file d'attente, cumuls.

    Rend un pic de charge visible AVANT qu'il ne devienne un incident :
    quand ``queued`` reste élevé longtemps (ou que ``failed`` monte), c'est
    le signe d'une vague d'auto-sync supérieure à la capacité.
    """
    return sync_executor.snapshot()


@router.get("/sync-jobs/{job_id}", response_model=SyncJobOut)
def get_sync_job(
    job_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de synchronisation introuvable.")

    assert_post_scope(db, current_user, job["post_id"])

    return _job_out(job, _job_items(db, job_id))


@router.get("/posts/{post_id}/sync-status", response_model=SyncJobOut | None)
def get_post_sync_status(
    post_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    assert_post_scope(db, current_user, post_id)

    job = db.execute(
        """
        SELECT * FROM sync_jobs
        WHERE post_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (post_id,),
    ).fetchone()

    if not job:
        return None

    return _job_out(job, _job_items(db, job["sync_job_id"]))


@router.post("/groups/{group_id}/sync")
def sync_group(
    group_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)

    try:
        assert_group_access(db, current_user, group_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    group = db.execute(
        "SELECT group_id FROM screen_groups WHERE group_id = %s",
        (group_id,),
    ).fetchone()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")

    post_ids = scoped_post_ids(
        db,
        [
            r["post_id"]
            for r in db.execute(
                "SELECT post_id FROM screen_group_posts WHERE group_id = %s ORDER BY post_id",
                (group_id,),
            ).fetchall()
        ],
        client_scope(db, current_user),
    )
    if not post_ids:
        raise HTTPException(status_code=400, detail="Le groupe ne contient aucun poste.")

    results = []
    submitted = []
    for pid in post_ids:
        running = service.check_running_sync(pid)
        if running:
            results.append({"post_id": pid, "status": "SKIPPED", "detail": "Déjà en cours."})
            continue
        job = service.create_job(pid, None)
        submitted.append((pid, job["sync_job_id"]))
        results.append({"post_id": pid, "status": "STARTED", "sync_job_id": job["sync_job_id"]})

    # Commit avant soumission (voir start_sync) : les workers doivent voir les
    # lignes sync_jobs créées, sinon succès fantôme.
    db.commit()
    for pid, job_id in submitted:
        sync_executor.submit(pid, job_id)

    return {"group_id": group_id, "results": results}


@router.get("/groups/{group_id}/media-hierarchy")
def get_group_media_hierarchy(
    group_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)
    try:
        assert_group_access(db, current_user, group_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    group = db.execute(
        "SELECT group_id FROM screen_groups WHERE group_id = %s",
        (group_id,),
    ).fetchone()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return {"group_id": group_id, "zones": service.get_group_media_hierarchy(group_id)}


@router.get("/groups/{group_id}/media-sync-status")
def get_group_media_sync_status(
    group_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)
    try:
        assert_group_access(db, current_user, group_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    group = db.execute(
        "SELECT group_id FROM screen_groups WHERE group_id = %s",
        (group_id,),
    ).fetchone()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return service.get_media_sync_states_for_group(group_id)


@router.post("/groups/{group_id}/media/{media_id}/sync")
def sync_group_media(
    group_id: int,
    media_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)

    try:
        assert_group_access(db, current_user, group_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    group = db.execute(
        "SELECT group_id FROM screen_groups WHERE group_id = %s",
        (group_id,),
    ).fetchone()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")

    media = db.execute(
        "SELECT media_id FROM media WHERE media_id = %s",
        (media_id,),
    ).fetchone()
    if not media:
        raise HTTPException(status_code=404, detail="Média introuvable.")

    # Le média doit être dans MON périmètre : l'accès au groupe ne vaut pas
    # accès à tous ses médias. Sans ce contrôle, un client pouvait déclencher
    # la synchronisation d'un média d'un autre client vers SES propres postes
    # (et donc le pousser en SFTP chez lui).
    try:
        assert_media_in_scope(db, client_scope(db, current_user),
                              current_user.user_id, media_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    post_ids = scoped_post_ids(
        db,
        [
            r["post_id"]
            for r in db.execute(
                "SELECT post_id FROM screen_group_posts WHERE group_id = %s ORDER BY post_id",
                (group_id,),
            ).fetchall()
        ],
        client_scope(db, current_user),
    )
    if not post_ids:
        raise HTTPException(status_code=400, detail="Le groupe ne contient aucun poste.")

    for pid in post_ids:
        try:
            db.execute(
                """
                INSERT INTO media_sync_state (media_id, post_id, status)
                VALUES (%s, %s, 'SYNCING')
                ON CONFLICT (media_id, post_id) DO UPDATE SET status = 'SYNCING'
                """,
                (media_id, pid),
            )
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        pass

    results = []
    submitted = []
    for pid in post_ids:
        running = service.check_running_sync(pid)
        if running:
            results.append({"post_id": pid, "status": "SKIPPED", "detail": "Déjà en cours."})
            try:
                db.execute(
                    """
                    INSERT INTO media_sync_state (media_id, post_id, status)
                    VALUES (%s, %s, 'NOT_SYNCED')
                    ON CONFLICT (media_id, post_id) DO UPDATE SET status = 'NOT_SYNCED'
                    """,
                    (media_id, pid),
                )
                db.commit()
            except Exception:
                pass
            break
        job = service.create_job(pid, None)
        submitted.append((pid, job["sync_job_id"]))
        results.append({"post_id": pid, "status": "STARTED", "sync_job_id": job["sync_job_id"]})

    # Commit avant soumission (voir start_sync) : les workers doivent voir les
    # lignes sync_jobs créées, sinon succès fantôme.
    try:
        db.commit()
    except Exception:
        pass
    for pid, job_id in submitted:
        sync_executor.submit(pid, job_id, [media_id])

    return {"group_id": group_id, "media_id": media_id, "results": results}


@router.get("/posts/{post_id}/config-preview")
def get_config_preview(
    post_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)
    assert_post_scope(db, current_user, post_id)
    try:
        config = service.generate_config(post_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return config


_last_load_log = 0.0


def _log_sync_load(submitted: int) -> None:
    """Log périodique (max 1/60 s) de l'état de la file, quand elle n'est pas vide."""
    global _last_load_log
    stats = sync_executor.snapshot()
    if submitted == 0 and stats["running"] == 0 and stats["queued"] == 0:
        return
    now = time.monotonic()
    if now - _last_load_log < 60.0:
        return
    _last_load_log = now
    logger.warning(
        "Scheduler : charge de sync — running=%s queued=%s max_workers=%s "
        "(soumis ce cycle=%s, total soumis=%s, terminés=%s, échecs=%s, pic file=%s)",
        stats["running"], stats["queued"], stats["max_workers"],
        submitted, stats["submitted_total"], stats["completed"],
        stats["failed"], stats["queue_peak"],
    )


def _scheduler_loop():
    while True:
        try:
            with get_sync_connection() as conn:
                service = SyncService(conn)
                try:
                    # Création des jobs programmés (synchro en différé) :
                    # idempotent, un job au plus par poste et par jour.
                    service.schedule_auto_syncs()
                except Exception as e:
                    logger.error(f"Auto-sync scheduling error: {e}", exc_info=True)
                due = service.get_due_scheduled_jobs()
                submitted = 0
                for job in due:
                    post_id = job["post_id"]
                    job_id = job["sync_job_id"]
                    if service.check_running_sync(post_id):
                        continue
                    service.mark_job_pending(job_id)
                    # Exécution bornée : au-delà de SYNC_MAX_WORKERS, le job
                    # attend dans la file de l'executor (il reste PENDING et
                    # sera exclu de la reprise des orphelins en 3.).
                    sync_executor.submit(post_id, job_id)
                    submitted += 1
                try:
                    # Reprise des jobs orphelins : les jobs jamais pris en charge
                    # par un worker (PENDING échoué, SCHEDULED non promu) sont
                    # marqués FAILED avec un message explicite. Log clairement
                    # visible quand un incident similaire se reproduit.
                    # Exclusion : les jobs en file/en cours dans l'executor
                    # borné ne sont PAS des orphelins (on ne les marque pas
                    # FAILED avant leur tour).
                    recovered = service.recover_orphan_jobs(
                        exclude_job_ids=sync_executor.active_job_ids()
                    )
                    if recovered:
                        logger.warning(
                            "Scheduler : %s job(s) orphelin(s) marqué(s) FAILED "
                            "(see JOB ORPHELIN logs).", recovered
                        )
                except Exception as e:
                    logger.error(f"Orphan-job recovery error: {e}", exc_info=True)
                _log_sync_load(submitted)
        except Exception as e:
            logger.error(f"Sync scheduler error: {e}", exc_info=True)
        time.sleep(15)


_scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
_scheduler_thread.start()