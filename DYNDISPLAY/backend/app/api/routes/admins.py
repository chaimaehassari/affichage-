from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_superadmin, require_admin
from app.schemas.auth import (
    AdminClientAssignRequest,
    AdminCreateRequest,
    AdminListItem,
    AdminListResponse,
    AdminUpdateRequest,
    ClientDetailResponse,
    ClientItem,
    ClientLicenseUpdateRequest,
    ClientListResponse,
    MessageResponse,
)
from app.services.scope import client_scope, site_in_scope
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1", tags=["Admins, Clients"])


def _client_in_scope(scope, client_code: str) -> bool:
    """Un client appartient-au périmètre si son code est dans le scope (None = global)."""
    return site_in_scope(scope, client_code)


def _client_item(client: dict) -> ClientDetailResponse:
    name = client.get("nom_client") or client.get("client_name")
    return ClientDetailResponse(
        client_id=client["client_id"],
        client_code=client["client_code"],
        client_name=name,
        license_sites=client.get("license_sites", 0),
        license_posts=client.get("license_posts", 0),
        user_count=client.get("user_count", 0),
        site_count=client.get("site_count", 0),
        activated_count=client.get("activated_count", 0),
        admins=client.get("admins") or [],
        admin_login=client.get("admin_login"),
        admin_code=client.get("admin_code"),
        created_at=client.get("created_at"),
    )


def _admin_item(admin: dict) -> AdminListItem:
    return AdminListItem(
        user_id=admin["user_id"],
        user_code=admin["user_code"],
        login=admin["login"],
        email=admin.get("email"),
        profile_id=admin["profile_id"],
        profile_name=admin["profile_name"] or "",
        is_active=admin["is_active"],
        is_superadmin=bool(admin.get("is_superadmin", False)),
        client_codes=admin.get("client_codes") or [],
        created_at=admin["created_at"].isoformat() if admin["created_at"] else None,
    )


# --- Gestion des Admins (Super Admin uniquement) ---


@router.get("/admins", response_model=AdminListResponse)
def list_admins(
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    admins = service.list_admins()
    items = []
    for a in admins:
        a["client_codes"] = service.get_admin_client_codes(a["user_id"])
        items.append(_admin_item(a))
    return AdminListResponse(admins=items, total=len(items))


@router.post("/admins", response_model=AdminListItem, status_code=201)
def create_admin(
    data: AdminCreateRequest,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    try:
        admin = service.create_admin(data, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    admin["client_codes"] = service.get_admin_client_codes(admin["user_id"])
    return _admin_item(admin)


@router.get("/admins/{admin_id}", response_model=AdminListItem)
def get_admin(
    admin_id: int,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    admin = service.get_admin(admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin introuvable.")
    if not admin["is_superadmin"]:
        admin["client_codes"] = service.get_admin_client_codes(admin_id)
    return _admin_item(admin)


@router.put("/admins/{admin_id}", response_model=AdminListItem)
def update_admin(
    admin_id: int,
    data: AdminUpdateRequest,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    if admin_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Le Super Admin ne peut pas modifier son propre compte.")
    service = UserService(db)
    try:
        admin = service.update_admin(admin_id, data, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    admin["client_codes"] = service.get_admin_client_codes(admin_id)
    return _admin_item(admin)


@router.delete("/admins/{admin_id}", response_model=MessageResponse)
def delete_admin(
    admin_id: int,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    service = UserService(db)
    try:
        service.delete_admin(admin_id, current_user.user_id)
        return MessageResponse(message="Admin supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Liste des Clients ---


@router.get("/clients", response_model=ClientListResponse)
def list_clients(
    current_user=Depends(require_admin),
    db: Connection = Depends(get_db),
):
    """Liste des clients.

    - Super Admin → tous les clients de l'application.
    - Admin classique → uniquement les clients qui lui sont affectés.
    """
    service = UserService(db)
    scope = client_scope(db, current_user)
    rows = service.list_clients(scope)
    items = []
    for r in rows:
        if not _client_in_scope(scope, r["client_code"]):
            continue
        detail = _client_item(r)
        items.append(ClientItem(
            client_id=detail.client_id,
            client_code=detail.client_code,
            client_name=detail.client_name,
            license_sites=detail.license_sites,
            license_posts=detail.license_posts,
            user_count=detail.user_count,
            site_count=detail.site_count,
            admin_login=detail.admin_login,
            admin_code=detail.admin_code,
            created_at=detail.created_at,
        ))
    return ClientListResponse(clients=items, total=len(items))


@router.get("/clients/{client_code}", response_model=ClientDetailResponse)
def get_client(
    client_code: str,
    current_user=Depends(require_admin),
    db: Connection = Depends(get_db),
):
    """Détail d'un client (licences, compteurs, admins affectés)."""
    service = UserService(db)
    scope = client_scope(db, current_user)
    client = service.get_client_by_code(client_code.upper())
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable.")
    if not _client_in_scope(scope, client_code):
        raise HTTPException(
            status_code=403,
            detail="Vous n'êtes pas autorisé à consulter ce client.",
        )
    return _client_item(client)


@router.put("/clients/{client_code}/license", response_model=ClientDetailResponse)
def update_client_license(
    client_code: str,
    data: ClientLicenseUpdateRequest,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    """Mise à jour des quotas de licences (sites / postes) d'un client.

    Réservé au Super Admin.
    """
    service = UserService(db)
    client = service.get_client_by_code(client_code.upper())
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable.")
    try:
        updated = service.update_client_license(
            client["client_id"], data.license_sites, data.license_posts,
            current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _client_item(updated)


@router.post("/admins/{admin_id}/clients", response_model=MessageResponse, status_code=201)
def assign_admin_to_client(
    admin_id: int,
    data: AdminClientAssignRequest,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    """Affecte un client à un Admin classique (Super Admin uniquement)."""
    service = UserService(db)
    try:
        service.assign_admin_to_client(admin_id, data.client_code, current_user.user_id)
        return MessageResponse(
            message=f"Client {data.client_code} affecté à l'admin."
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/admins/{admin_id}/clients/{client_code}", response_model=MessageResponse)
def remove_admin_from_client(
    admin_id: int,
    client_code: str,
    current_user=Depends(require_superadmin),
    db: Connection = Depends(get_db),
):
    """Retire un client des clients gérés par un Admin (Super Admin uniquement)."""
    service = UserService(db)
    try:
        service.remove_admin_from_client(
            admin_id, client_code.upper(), current_user.user_id
        )
        return MessageResponse(
            message=f"Client {client_code} retiré de l'admin."
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))