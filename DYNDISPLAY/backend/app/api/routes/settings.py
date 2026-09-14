from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Connection
from datetime import datetime, timezone

from app.db.database import get_db
from app.dependencies.auth import get_current_user_dependency, require_permission
from app.core.security import verify_password, hash_password, verify_supreme_admin_code
from app.schemas.settings import (
    SettingsOut, SettingsUpdate, ClientCodeVerify, ChangePasswordRequest,
    LicenseUpdateRequest, AccessPasswordVerify, ChangeAccessPasswordRequest,
    FtpProfileCreate, FtpProfileUpdate, FtpProfileOut, FtpTestRequest, FtpTestResult,
)
from app.services.settings_service import SettingsService, FtpProfileService
from app.services.user_service import UserService
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1", tags=["Settings"])


@router.post("/settings/verify-client-code")
def verify_client_code(
    payload: ClientCodeVerify,
    current_user=Depends(get_current_user_dependency),
    db: Connection = Depends(get_db),
):
    user = db.execute(
        "SELECT password_hash FROM users WHERE user_id = %s",
        (current_user.user_id,),
    ).fetchone()
    if not user or not verify_password(payload.code, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")
    return {"valid": True}


@router.post("/settings/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user=Depends(get_current_user_dependency),
    db: Connection = Depends(get_db),
):
    user = db.execute(
        "SELECT * FROM users WHERE user_id = %s",
        (current_user.user_id,),
    ).fetchone()
    if not user or not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect.")

    if payload.new_password == user["login"]:
        raise HTTPException(status_code=400, detail="Le mot de passe doit être différent du login.")

    service = UserService(db)
    try:
        service._validate_password_history(current_user.user_id, payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_hash = hash_password(payload.new_password)
    db.execute(
        """
        UPDATE users
        SET password_hash = %s, must_change_password = FALSE, failed_attempts = 0,
            locked_until = NULL, last_password_change_at = %s, updated_at = %s
        WHERE user_id = %s
        """,
        (new_hash, datetime.now(timezone.utc),
         datetime.now(timezone.utc), current_user.user_id),
    )
    service._add_password_history(current_user.user_id, new_hash)
    service._trim_password_history(current_user.user_id)

    return {"success": True, "message": "Mot de passe modifié avec succès."}


@router.post("/settings/verify-access")
def verify_access_password(
    payload: AccessPasswordVerify,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
    request: Request = None,
):
    service = SettingsService(db)
    if not service.verify_access_password(payload.password, current_user.login):
        log_action(db, current_user.user_id, "supreme_admin_access_denied", "settings", None,
                   "Tentative d'accès paramètres échouée (code incorrect)",
                   ip_address=request.client.host if request and request.client else None)
        raise HTTPException(status_code=401, detail="Mot de passe d'accès incorrect.")
    log_action(db, current_user.user_id, "supreme_admin_access_granted", "settings", None,
               "Accès paramètres autorisé",
               ip_address=request.client.host if request and request.client else None)
    return {"valid": True}


@router.post("/settings/change-access-password")
def change_access_password(
    payload: ChangeAccessPasswordRequest,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    user = db.execute(
        """
        SELECT u.*, p.name AS profile_name
        FROM users u
        JOIN profiles p ON p.profile_id = u.profile_id
        WHERE u.user_id = %s
        """,
        (current_user.user_id,),
    ).fetchone()
    if not user or user["profile_name"] != "Administrateur":
        raise HTTPException(status_code=403, detail="Seul un Administrateur peut modifier ce mot de passe.")

    service = SettingsService(db)
    if not service.verify_access_password(payload.current_password):
        raise HTTPException(status_code=400, detail="Mot de passe d'accès actuel incorrect.")
    service.set_access_password(payload.new_password)
    log_action(db, current_user.user_id, "change_access_password", "general_settings", None,
               "Modification du mot de passe d'accès aux paramètres")
    return {"success": True, "message": "Mot de passe d'accès aux paramètres modifié."}


@router.post("/settings/regenerate-client-code")
def regenerate_client_code(
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    import secrets
    new_code = secrets.token_hex(4).upper()
    service = SettingsService(db)
    result = service.update_settings({"code_client": new_code})
    used = service.count_used_licenses()
    result["used_sites"] = used["used_sites"]
    result["used_posts"] = used["used_posts"]
    return result


@router.get("/settings")
def get_settings(
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = SettingsService(db)
    settings = service.get_all_settings()
    used = service.count_used_licenses()
    settings["used_sites"] = used["used_sites"]
    settings["used_posts"] = used["used_posts"]
    return settings


@router.put("/settings")
def update_settings(
    payload: SettingsUpdate,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = SettingsService(db)
    data = payload.model_dump(exclude_unset=True)
    result = service.update_settings(data)
    used = service.count_used_licenses()
    result["used_sites"] = used["used_sites"]
    result["used_posts"] = used["used_posts"]
    return result


@router.post("/settings/license/update")
def update_licenses(
    payload: LicenseUpdateRequest,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = SettingsService(db)
    try:
        result = service.update_licenses(payload.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    used = service.count_used_licenses()
    result["used_sites"] = used["used_sites"]
    result["used_posts"] = used["used_posts"]
    log_action(db, current_user.user_id, "update_licenses", "general_settings", None,
               f"Licences modifiées : {payload.sites} sites, {payload.posts} postes")
    return result


@router.get("/ftp-profiles")
def list_ftp_profiles(
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = FtpProfileService(db)
    return service.list_profiles()


@router.post("/ftp-profiles", status_code=201)
def create_ftp_profile(
    payload: FtpProfileCreate,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = FtpProfileService(db)
    try:
        return service.create_profile(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/ftp-profiles/{profile_id}")
def update_ftp_profile(
    profile_id: int,
    payload: FtpProfileUpdate,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = FtpProfileService(db)
    try:
        return service.update_profile(profile_id, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/ftp-profiles/{profile_id}")
def delete_ftp_profile(
    profile_id: int,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = FtpProfileService(db)
    try:
        service.delete_profile(profile_id)
        return {"message": "Profil supprimé."}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/settings/test-ftp")
def test_ftp(
    payload: FtpTestRequest,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = FtpProfileService(db)
    return service.test_connection(payload.profile_id)