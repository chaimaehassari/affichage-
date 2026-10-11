from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_permission, require_superadmin
from app.schemas.auth import (
    ClientItem,
    ClientListResponse,
    MessageResponse,
    PermissionListItem,
    ProfileInfo,
    UserCreateRequest,
    UserCreatedResponse,
    UserDetailResponse,
    UserListResponse,
    UserListItem,
    UserUpdateRequest,
    PasswordResetRequest,
)
from app.services.audit_service import log_action
from app.services.scope import (
    admin_client_codes,
    client_scope,
    is_regular_admin,
    site_in_scope,
    target_user_in_scope,
    user_owner_user_id,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


def _check_scope(db, current_user, *, target_user_id=None):
    """Vérifie qu'un compte cible appartient au périmètre de l'utilisateur connecté.

    Source de vérité unique : `target_user_in_scope()` (voir scope.py), utilisée
    aussi bien par la liste que par l'édition et la suppression. Avant, la liste
    et l'édition appliquaient deux règles différentes — un compte pouvait être
    listé puis refusé à la modification.
    """
    if target_user_in_scope(db, current_user, target_user_id):
        return
    if is_regular_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez gérer que les utilisateurs qui vous sont affectés.",
        )
    raise HTTPException(
        status_code=403,
        detail="Ce compte ne fait pas partie de votre périmètre.",
    )


@router.get("", response_model=UserListResponse)
def list_users(
    search: str | None = Query(None),
    current_user=Depends(require_permission("user_list")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    users = service.list_users(search, client_scope(db, current_user), user_owner_user_id(current_user))
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
            is_superadmin=bool(u.get("is_superadmin", False)),
            created_at=u["created_at"].isoformat() if u["created_at"] else None,
            client_name=u.get("client_name"),
            admin_id=u.get("admin_id"),
            admin_login=u.get("admin_login"),
            admin_code=u.get("admin_code"),
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

    _check_scope(db, current_user, target_user_id=user_id)

    zones = service.get_user_zones(user_id)
    groups = service.get_user_groups(user_id)
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
        is_superadmin=bool(user.get("is_superadmin", False)),
        admin_id=user.get("admin_id"),
        created_at=user["created_at"].isoformat() if user["created_at"] else None,
        updated_at=user["updated_at"].isoformat() if user["updated_at"] else None,
        last_login_at=user["last_login_at"].isoformat() if user["last_login_at"] else None,
        zones=zones,
        groups=groups,
        permissions=permissions,
    )


@router.post("", response_model=UserCreatedResponse, status_code=201)
def create_user(
    data: UserCreateRequest,
    current_user=Depends(require_permission("user_create")),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    if is_regular_admin(current_user):
        # Un Admin classique ne rattache un compte qu'à un client de son
        # périmètre. Créer un client se fait explicitement via POST
        # /api/v1/clients (source unique, auto-affectation à l'admin) : un
        # code hors périmètre — qu'il existe déjà (client d'un autre admin)
        # ou qu'il soit inconnu — est donc refusé, sans jamais affecter ou
        # créer de client à la volée ici.
        data.admin_id = current_user.user_id
        codes = admin_client_codes(db, current_user)
        requested = (data.user_code or "").strip().upper()
        if requested:
            if not site_in_scope(codes, requested):
                raise HTTPException(
                    status_code=400,
                    detail="Ce code client ne figure pas dans votre périmètre : "
                           "créez le client via POST /api/v1/clients avant de "
                           "rattacher un utilisateur.",
                )
            data.user_code = requested
        elif len(codes) == 1:
            data.user_code = codes[0]
        elif not codes:
            raise HTTPException(
                status_code=400,
                detail="Aucun client ne vous est affecté : saisissez le code "
                       "d'un nouveau client pour le créer.",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Sélectionnez le client de rattachement du compte "
                       f"parmi : {', '.join(codes)}.",
            )
    # Pas de _check_scope ici : le compte n'existe pas encore, son rattachement
    # vient d'être validé ci-dessus (client de l'admin + admin_id forcé).
    try:
        user = service.create_user(data, current_user.user_id)
        return UserCreatedResponse(
            message=f"Utilisateur {user['login']} créé avec succès.",
            user_id=user["user_id"],
            login=user["login"],
            user_code=user.get("user_code"),
        )
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
    _check_scope(db, current_user, target_user_id=user_id)
    if is_regular_admin(current_user):
        # Un Admin classique ne peut pas transferer la propriete d'un compte
        # vers un autre administrateur : `admin_id` est la colonne qui definit
        # l'appartenance d'un compte, donc la seule colonne qui pilote
        # l'isolation de `GET /users`. On la force a sa valeur actuelle, ce qui
        # neutralise un `admin_id` arbitraire envoye dans le corps de la
        # requete. Le Super Admin, lui, conserve ce pouvoir.
        data.admin_id = service.get_user(user_id).get("admin_id")
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
    existing = service.get_user(user_id)
    if existing:
        _check_scope(db, current_user, target_user_id=user_id)
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
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Utilisez le changement de mot de passe depuis votre compte pour modifier votre propre mot de passe.",
        )
    if data.new_password != data.password_confirm:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas.")

    service = UserService(db)
    # Controle inconditionnel (comme sur `PUT`) : le conditionner a
    # l'existence du compte laissait passer un identifiant inconnu, et
    # exposait au passage l'existence ou non d'un `user_id` via le code
    # de reponse.
    _check_scope(db, current_user, target_user_id=user_id)
    try:
        service.reset_password(user_id, data.new_password, current_user.user_id)
        return MessageResponse(message="Mot de passe réinitialisé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))