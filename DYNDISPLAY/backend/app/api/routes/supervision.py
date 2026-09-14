from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_permission, require_activated
from app.schemas.supervision import SupervisionSiteOut, HeartbeatRequest
from app.services.supervision_service import SupervisionService

router = APIRouter(prefix="/api/v1", tags=["Supervision"])


@router.get("/supervision")
def get_supervision(
    current_user=Depends(require_permission("menu_config")),
    current_user_activated=Depends(require_activated),
    db: Connection = Depends(get_db),
):
    service = SupervisionService(db)
    return service.get_supervision_data()


@router.post("/posts/heartbeat")
def send_heartbeat(
    payload: HeartbeatRequest,
    db: Connection = Depends(get_db),
):
    service = SupervisionService(db)
    ok = service.send_heartbeat(payload.post_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Poste introuvable.")
    return {"message": "Heartbeat reçu."}


@router.post("/posts/{post_id}/ping")
def ping_post(
    post_id: int,
    current_user=Depends(require_permission("menu_config")),
    current_user_activated=Depends(require_activated),
    db: Connection = Depends(get_db),
):
    service = SupervisionService(db)
    return service.ping_post(post_id)