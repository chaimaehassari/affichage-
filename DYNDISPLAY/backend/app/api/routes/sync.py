import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from app.db.database import get_db, connect_new
from app.dependencies.auth import require_permission
from app.schemas.sync import SyncJobOut, SyncJobCreate
from app.services.sync_service import SyncService
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

    if scheduled_at is None:
        thread = threading.Thread(target=_run_sync_task, args=(post_id, job_id), daemon=True)
        thread.start()

    return _job_out(job, [])


def _run_sync_task(post_id: int, job_id: int, media_ids: list[int] | None = None):
    try:
        with connect_new() as conn:
            service = SyncService(conn)
            service.run_sync(post_id, job_id, media_ids=media_ids)
    except Exception as e:
        logger.error(f"Sync thread failed for job {job_id}: {e}", exc_info=True)


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

    return _job_out(job, _job_items(db, job_id))


@router.get("/posts/{post_id}/sync-status", response_model=SyncJobOut | None)
def get_post_sync_status(
    post_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
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

    group = db.execute(
        "SELECT group_id FROM screen_groups WHERE group_id = %s",
        (group_id,),
    ).fetchone()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")

    post_ids = [
        r["post_id"]
        for r in db.execute(
            "SELECT post_id FROM screen_group_posts WHERE group_id = %s ORDER BY post_id",
            (group_id,),
        ).fetchall()
    ]
    if not post_ids:
        raise HTTPException(status_code=400, detail="Le groupe ne contient aucun poste.")

    results = []
    for pid in post_ids:
        running = service.check_running_sync(pid)
        if running:
            results.append({"post_id": pid, "status": "SKIPPED", "detail": "Déjà en cours."})
            continue
        job = service.create_job(pid, None)
        job_id = job["sync_job_id"]
        thread = threading.Thread(target=_run_sync_task, args=(pid, job_id), daemon=True)
        thread.start()
        results.append({"post_id": pid, "status": "STARTED", "sync_job_id": job_id})

    return {"group_id": group_id, "results": results}


@router.get("/groups/{group_id}/media-hierarchy")
def get_group_media_hierarchy(
    group_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)
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

    post_ids = [
        r["post_id"]
        for r in db.execute(
            "SELECT post_id FROM screen_group_posts WHERE group_id = %s ORDER BY post_id",
            (group_id,),
        ).fetchall()
    ]
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
        job_id = job["sync_job_id"]
        thread = threading.Thread(
            target=_run_sync_task, args=(pid, job_id, [media_id]), daemon=True
        )
        thread.start()
        results.append({"post_id": pid, "status": "STARTED", "sync_job_id": job_id})

    return {"group_id": group_id, "media_id": media_id, "results": results}


@router.get("/posts/{post_id}/config-preview")
def get_config_preview(
    post_id: int,
    current_user=Depends(require_permission("menu_sync")),
    db: Connection = Depends(get_db),
):
    service = SyncService(db)
    try:
        config = service.generate_config(post_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return config


def _scheduler_loop():
    while True:
        try:
            with connect_new() as conn:
                service = SyncService(conn)
                try:
                    # Création des jobs programmés (synchro en différé) :
                    # idempotent, un job au plus par poste et par jour.
                    service.schedule_auto_syncs()
                except Exception as e:
                    logger.error(f"Auto-sync scheduling error: {e}", exc_info=True)
                due = service.get_due_scheduled_jobs()
                for job in due:
                    post_id = job["post_id"]
                    job_id = job["sync_job_id"]
                    if service.check_running_sync(post_id):
                        continue
                    service.mark_job_pending(job_id)
                    thread = threading.Thread(
                        target=_run_sync_task, args=(post_id, job_id), daemon=True
                    )
                    thread.start()
        except Exception as e:
            logger.error(f"Sync scheduler error: {e}", exc_info=True)
        time.sleep(15)


_scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
_scheduler_thread.start()