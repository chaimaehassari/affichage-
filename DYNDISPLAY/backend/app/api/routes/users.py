from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_permission
from app.schemas.auth import (
    MessageResponse,
    PermissionListItem,
    ProfileInfo,
    UserCreateRequest,
    UserDetailResponse,
    UserListResponse,
    UserListItem,
    UserUpdateRequest,
    PasswordResetRequest,
)
from app.services.audit_service import log_action
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("", response_model=UserListResponse)
def list_users(
    search: str | None = Query(None),
    current_user=Depends(require_permission("user_list")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    users = service.list_users(search)
    items = []
    for u in users:
        items.append(UserListItem(
            user_id=u["user_id"],
            user_code=u["user_code"],
            login=u["login"],
            email=u.get("email"),
            password_masked="••••••••",
            profile_id=u["profile_id"],
            profile_name=u["profile_name"] or "",
            is_active=u["is_active"],
            is_activated=bool(u.get("is_activated", True)),
            sites_limit=u.get("sites_limit"),
            posts_limit=u.get("posts_limit"),
            created_at=u["created_at"].isoformat() if u["created_at"] else None,
        ))
    return UserListResponse(users=items, total=len(items))


@router.get("/profiles", response_model=list[ProfileInfo])
def list_profiles(
    current_user=Depends(require_permission("user_list")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    profiles = service.get_profiles()
    return [ProfileInfo(
        profile_id=p["profile_id"],
        name=p["name"],
        description=p["description"],
        is_active=p["is_active"],
    ) for p in profiles]


@router.get("/permissions", response_model=list[PermissionListItem])
def list_permissions(
    current_user=Depends(require_permission("user_list")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    perms = service.get_all_permissions()
    return [PermissionListItem(
        permission_id=p["permission_id"],
        code=p["code"],
        name=p["name"],
        description=p["description"],
        is_active=p["is_active"],
    ) for p in perms]


@router.get("/{user_id}", response_model=UserDetailResponse)
def get_user(
    user_id: int,
    current_user=Depends(require_permission("user_list")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    user = service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    zones = service.get_user_zones(user_id)
    permissions = service.get_user_permissions(user_id)

    return UserDetailResponse(
        user_id=user["user_id"],
        user_code=user["user_code"],
        login=user["login"],
        email=user.get("email"),
        profile_id=user["profile_id"],
        profile_name=user["profile_name"] or "",
        is_active=user["is_active"],
        must_change_password=user["must_change_password"],
        is_activated=bool(user.get("is_activated", True)),
        sites_limit=user.get("sites_limit"),
        posts_limit=user.get("posts_limit"),
        activated_at=user["activated_at"].isoformat() if user.get("activated_at") else None,
        created_at=user["created_at"].isoformat() if user["created_at"] else None,
        updated_at=user["updated_at"].isoformat() if user["updated_at"] else None,
        last_login_at=user["last_login_at"].isoformat() if user["last_login_at"] else None,
        zones=zones,
        permissions=permissions,
    )


@router.post("", response_model=MessageResponse, status_code=201)
def create_user(
    data: UserCreateRequest,
    current_user=Depends(require_permission("user_create")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    try:
        user = service.create_user(data, current_user.user_id)
        return MessageResponse(message=f"Utilisateur {user['login']} créé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}", response_model=MessageResponse)
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    current_user=Depends(require_permission("user_update")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    try:
        user = service.update_user(user_id, data, current_user.user_id)
        return MessageResponse(message=f"Utilisateur {user['login']} modifié avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    current_user=Depends(require_permission("user_delete")),
    db: Connection = Depends(get_db),
):
    if current_user.user_id == user_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte.")

    service = UserService(db)
    try:
        service.delete_user(user_id, current_user.user_id)
        return MessageResponse(message="Utilisateur supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
def reset_password(
    user_id: int,
    data: PasswordResetRequest,
    current_user=Depends(require_permission("user_update")),
    db: Connection = Depends(get_db),
):
    if data.new_password != data.password_confirm:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas.")

    service = UserService(db)
    try:
        service.reset_password(user_id, data.new_password, current_user.user_id)
        return MessageResponse(message="Mot de passe réinitialisé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))