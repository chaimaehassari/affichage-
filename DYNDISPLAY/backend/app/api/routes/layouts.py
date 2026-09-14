from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_permission
from app.schemas.layout import (
    LayoutCreate,
    LayoutDetailOut,
    LayoutOut,
    LayoutUpdate,
    MessageResponse,
)
from app.services.layout_service import LayoutService

router = APIRouter(prefix="/api/v1", tags=["Layouts"])


def _layout_out(layout) -> LayoutOut:
    return LayoutOut(
        layout_id=layout["layout_id"],
        name=layout["name"],
        is_active=layout["is_active"],
        active_zone_count=layout["active_zone_count"] or 0,
        created_at=layout["created_at"].isoformat() if layout["created_at"] else None,
        updated_at=layout["updated_at"].isoformat() if layout["updated_at"] else None,
    )


@router.get("/layouts", response_model=list[LayoutOut])
def list_layouts(
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    service = LayoutService(db)
    return [_layout_out(l) for l in service.list_layouts()]


@router.post("/layouts", response_model=LayoutDetailOut, status_code=201)
def create_layout(
    data: LayoutCreate,
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    service = LayoutService(db)
    try:
        layout = service.create_layout(data)
        return service.get_layout_detail(layout["layout_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/layouts/{layout_id}", response_model=LayoutDetailOut)
def get_layout(
    layout_id: int,
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    service = LayoutService(db)
    result = service.get_layout_detail(layout_id)
    if not result:
        raise HTTPException(status_code=404, detail="Modèle introuvable.")
    return result


@router.put("/layouts/{layout_id}", response_model=LayoutDetailOut)
def update_layout(
    layout_id: int,
    data: LayoutUpdate,
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    service = LayoutService(db)
    try:
        service.update_layout(layout_id, data)
        return service.get_layout_detail(layout_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/layouts/{layout_id}", response_model=MessageResponse)
def delete_layout(
    layout_id: int,
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    service = LayoutService(db)
    try:
        service.delete_layout(layout_id)
        return MessageResponse(message="Modèle supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))