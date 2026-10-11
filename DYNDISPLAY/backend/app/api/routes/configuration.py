from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_permission
from app.schemas.configuration import (
    PostConfigurationOut,
    PostConfigurationUpdate,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
    ZoneMediaAssignment,
)
from app.services.configuration_service import ConfigurationService, ScheduleService
from app.services.scope import assert_post_scope, client_scope

router = APIRouter(prefix="/api/v1", tags=["Configuration"])


def _assert_schedule_scope(db, current_user, schedule_id: int) -> None:
    row = db.execute(
        "SELECT post_id FROM schedules WHERE schedule_id = %s",
        (schedule_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Planning introuvable.")
    _assert_post_scope(db, current_user, row["post_id"])


def _assert_post_scope(db, current_user, post_id: int) -> None:
    try:
        assert_post_scope(db, current_user, post_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/posts/{post_id}/configuration", response_model=PostConfigurationOut)
def get_post_configuration(
    post_id: int,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_post_scope(db, current_user, post_id)
    service = ConfigurationService(db)
    result = service.get_configuration(post_id)
    if not result:
        raise HTTPException(status_code=404, detail="Poste introuvable.")
    return result


@router.put("/posts/{post_id}/configuration", response_model=PostConfigurationOut)
def update_post_configuration(
    post_id: int,
    data: PostConfigurationUpdate,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_post_scope(db, current_user, post_id)
    service = ConfigurationService(db)
    try:
        return service.update_configuration(post_id, data, user_id=current_user.user_id,
                                             scope=client_scope(db, current_user))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/posts/{post_id}/zones")
def update_post_zones(
    post_id: int,
    zones: list[ZoneMediaAssignment],
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_post_scope(db, current_user, post_id)
    service = ConfigurationService(db)
    try:
        service.update_zones(post_id, zones, user_id=current_user.user_id,
                             scope=client_scope(db, current_user))
        return {"message": "Zones mises à jour avec succès."}
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/posts/{post_id}/schedules", response_model=list[ScheduleOut])
def list_schedules(
    post_id: int,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_post_scope(db, current_user, post_id)
    service = ScheduleService(db)
    return service.list_schedules(post_id)


@router.post("/posts/{post_id}/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(
    post_id: int,
    data: ScheduleCreate,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_post_scope(db, current_user, post_id)
    service = ScheduleService(db)
    try:
        return service.create_schedule(post_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_schedule_scope(db, current_user, schedule_id)
    service = ScheduleService(db)
    try:
        return service.update_schedule(schedule_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    _assert_schedule_scope(db, current_user, schedule_id)
    service = ScheduleService(db)
    try:
        service.delete_schedule(schedule_id)
        return {"message": "Planning supprimé avec succès."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))