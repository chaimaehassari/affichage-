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


@router.get("/layouts", response_model=list[LayoutOut] | list[LayoutDetailOut])
def list_layouts(
    include_zones: bool = False,
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    """Liste les modèles de découpage.

    `include_zones=true` renvoie en plus les zones de chaque modèle. L'écran de
    configuration en a besoin pour tous les modèles, pas seulement celui
    sélectionné : sans ce lot, il déclenchait un GET /layouts/{id} par modèle
    (plus de 700 requêtes en série), chacune avec son propre risque de 401.
    """
    service = LayoutService(db)
    if include_zones:
        return service.list_layouts_with_zones()
    return [_layout_out(l) for l in service.list_layouts()]


@router.post("/layouts", response_model=LayoutDetailOut, status_code=201)
def create_layout(
    data: LayoutCreate,
    current_user=Depends(require_permission("menu_conception")),
    db: Connection = Depends(get_db),
):
    """Crée un modèle de découpage.

    Accessible à tout utilisateur disposant de la permission `menu_conception`
    (l'écran Découpage) : chaque utilisateur autorisé peut enregistrer son
    propre modèle.
    """
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
    """Modifie un modèle — accessible à tout utilisateur avec `menu_conception`."""
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
    """Supprime un modèle — accessible à tout utilisateur avec `menu_conception`."""
    service = LayoutService(db)
    try:
        service.delete_layout(layout_id)
        return MessageResponse(message="Modèle supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))