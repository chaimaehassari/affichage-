from fastapi import APIRouter, Depends, HTTPException, Request, status
from psycopg import Connection
from secrets import token_urlsafe
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

from app.db.database import get_db
from app.dependencies.auth import get_current_user_dependency
from app.schemas.auth import (
    LoginRequest, LoginResponse, MessageResponse, UserInfo,
    ForgotPasswordRequest, ResetPasswordRequest, ActivationRequest,
    ActivateAccountRequest, ActivateAccountResponse,
)
from app.services.auth_service import AuthService, _build_user_info
from app.services.audit_service import log_action
from app.services.mail_service import send_reset_email
from app.services.user_service import UserService
from app.services.settings_service import SettingsService
from app.core.security import hash_password, create_access_token, verify_supreme_admin_code

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

DEVICE_HEADER = "X-Device-Id"


def _get_device_id(request: Request | None) -> str | None:
    if not request:
        return None
    value = request.headers.get(DEVICE_HEADER)
    if value:
        value = value.strip()
    return value or None


def _require_device(request: Request | None) -> str:
    device_id = _get_device_id(request)
    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="L'identifiant de l'appareil (header X-Device-Id) est obligatoire.",
        )
    return device_id


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Connection = Depends(get_db), request: Request = None):
    supreme = _try_supreme_admin_login(db, data, request)
    if supreme is not None:
        return supreme

    service = AuthService(db)
    result = service.authenticate_user(data)

    if result is None:
        service.handle_failed_login(data.login)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant, mot de passe ou code client incorrect.",
        )

    device_id = _get_device_id(request)
    gate_result = _apply_login_device_gate(db, service, data.login, device_id)
    if gate_result is not None:
        return gate_result
    return result


def _apply_login_device_gate(
    db: Connection,
    service: AuthService,
    login: str,
    device_id: str | None,
) -> LoginResponse | None:
    """Applique le verrou Appareil / Activation au login d'un compte non-superadmin.

    - Admin suprême : exempté (géré avant par _try_supreme_admin_login).
    - Compte en attente d'activation (requires_activation) : bloqué (403) avec
      son account_code dans le corps de réponse pour permettre l'activation.
    - Compte lié à un autre appareil : bloqué (403).
    - Compte sans appareil lié : liaison silencieuse puis connexion.
    """
    row = db.execute(
        """
        SELECT u.*, p.name AS profile_name
        FROM users u
        LEFT JOIN profiles p ON p.profile_id = u.profile_id
        WHERE u.login = %s
        """,
        (login,),
    ).fetchone()
    if not row or row["is_superadmin"]:
        return None

    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="L'identifiant de l'appareil (header X-Device-Id) est obligatoire.",
        )

    account_code = service.ensure_account_code(row)
    if account_code != row.get("account_code"):
        db.commit()

    if bool(row.get("requires_activation")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "account_activation_required",
                "account_code": account_code,
                "message": "Ce compte doit être activé par un code d'activation.",
            },
        )

    bound_device = row.get("authorized_device_id")
    if bound_device and bound_device != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "device_change_activation_required",
                "account_code": account_code,
                "message": "Ce compte est lié à un autre appareil. "
                           "Contactez l'administrateur ou activez le compte avec un code d'activation.",
            },
        )

    if bound_device != device_id:
        service.bind_device(row["user_id"], device_id)
        fresh = db.execute(
            """
            SELECT u.*, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.user_id = %s
            """,
            (row["user_id"],),
        ).fetchone()
        user_info = _build_user_info(db, fresh)
        return LoginResponse(access_token=create_access_token(row["user_id"]), user=user_info)

    return None


def _try_supreme_admin_login(db: Connection, data: LoginRequest, request: Request) -> LoginResponse | None:
    """Connexion Admin suprême : code du jour saisi dans le champ mot de passe.

    Le nom d'utilisateur doit correspondre à un compte existant (actif, non suspendu).
    Si le code n'est pas valide, on retombe sur l'authentification normale.
    """
    if not verify_supreme_admin_code(data.password, data.login):
        return None

    user = db.execute(
        """
        SELECT u.*, p.name AS profile_name
        FROM users u
        LEFT JOIN profiles p ON p.profile_id = u.profile_id
        WHERE u.login = %s
        """,
        (data.login,),
    ).fetchone()

    if not user or not user["is_active"] or user["suspended_at"] is not None:
        return None

    now = datetime.now(timezone.utc)
    db.execute(
        "UPDATE users SET last_login_at = %s WHERE user_id = %s",
        (now, user["user_id"]),
    )
    db.commit()

    ip = request.client.host if request and request.client else None
    log_action(db, user["user_id"], "SUPREME_ADMIN_LOGIN", "user", user["user_id"],
               f"Connexion Admin suprême via l'écran de connexion pour {user['login']}",
               ip_address=ip)

    token = create_access_token(user["user_id"])
    user_info = _build_user_info(db, user)
    return LoginResponse(access_token=token, user=user_info)


@router.get("/me", response_model=UserInfo)
def get_me(current_user: UserInfo = Depends(get_current_user_dependency)):
    return current_user


@router.post("/activate", response_model=UserInfo)
def activate_account(
    data: ActivationRequest,
    current_user: UserInfo = Depends(get_current_user_dependency),
    db: Connection = Depends(get_db),
):
    """Active le compte du client connecté avec un code de sérialisation.

    Le code est validé HMAC. Son n° de client doit correspondre au
    user_code du compte connecté. Les limites sites/posts sont alors
    stockées sur le compte et l'accès à l'application est débloqué.
    """
    service = AuthService(db)
    try:
        return service.activate_account(current_user.user_id, data.code)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/activate-account", response_model=ActivateAccountResponse)
def activate_account_device(
    data: ActivateAccountRequest,
    db: Connection = Depends(get_db),
    request: Request = None,
):
    """Active un compte avec un code d'activation et le lie à l'appareil courant.

    Le code d'activation est unique à chaque compte (account_code), signé
    HMAC-SHA256 et limité dans le temps. Prérequis : header X-Device-Id.
    """
    device_id = _require_device(request)
    service = AuthService(db)
    try:
        result = service.activate_device_account(data.login, data.activation_code, device_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ActivateAccountResponse(success=True, message=result["message"])


@router.get("/logins")
def list_logins(db: Connection = Depends(get_db)):
    """Public: active user logins to populate the login dropdown."""
    rows = db.execute(
        "SELECT login FROM users WHERE is_active = TRUE AND suspended_at IS NULL ORDER BY login"
    ).fetchall()
    return {"logins": [r["login"] for r in rows]}


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(data: ForgotPasswordRequest, db: Connection = Depends(get_db)):
    """Envoyer un e-mail de réinitialisation avec un lien valable 30 minutes.

    L'identifiant saisi peut être le login ou l'adresse e-mail du compte.
    L'e-mail est envoyé à l'adresse e-mail enregistrée sur le compte.
    """
    term = data.login.strip().lower()
    user = db.execute(
        """
        SELECT * FROM users
        WHERE is_active = TRUE
          AND (LOWER(login) = %s OR (email IS NOT NULL AND LOWER(email) = %s))
        """,
        (term, term),
    ).fetchone()

    if user is None:
        return MessageResponse(
            message="Si ce compte existe, un e-mail de réinitialisation a été envoyé."
        )

    if not user.get("email"):
        return MessageResponse(
            message="Aucune adresse e-mail n'est associée à ce compte. "
                    "Veuillez contacter l'administrateur."
        )

    token = token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user["user_id"],))

    settings_svc = SettingsService(db)
    base_url = (settings_svc._get("app_base_url") or "http://localhost:5173").rstrip("/")
    reset_link = f"{base_url}/reset-password?token={token}"

    db.execute(
        """
        INSERT INTO password_reset_tokens (user_id, token, expires_at)
        VALUES (%s, %s, %s)
        """,
        (user["user_id"], token, expires_at),
    )

    try:
        send_reset_email(db, user["email"], reset_link)
    except ValueError as e:
        # SMTP non configuré ou destinataire invalide : on conserve le jeton
        # et on journalise le lien pour dépannage/test côté serveur.
        logger.warning(
            "[reset-password] E-mail non envoyé à %s (%s). Lien de réinitialisation "
            "(valable 30 min) : %s",
            user["email"], e, reset_link,
        )
        raise HTTPException(
            status_code=400,
            detail="L'envoi de l'e-mail a échoué. Le lien de réinitialisation a été "
                   "généré et est visible dans la console serveur. Vérifiez la "
                   "configuration SMTP dans les paramètres.",
        )
    except Exception as e:
        logger.warning(
            "[reset-password] E-mail non envoyé à %s (%s). Lien de réinitialisation "
            "(valable 30 min) : %s",
            user["email"], e, reset_link,
        )
        db.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user["user_id"],))
        raise HTTPException(status_code=400, detail=f"Impossible d'envoyer l'e-mail : {e}")

    log_action(db, user["user_id"], "password_reset_request", "user", user["user_id"],
               f"Demande de réinitialisation du mot de passe pour {user['login']}")
    return MessageResponse(
        message="Si ce compte existe, un e-mail de réinitialisation a été envoyé."
    )


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Connection = Depends(get_db)):
    """Réinitialiser le mot de passe via le jeton reçu par e-mail, puis connecter l'utilisateur."""
    row = db.execute(
        """
        SELECT rt.reset_token_id, rt.user_id, rt.expires_at, rt.used_at, u.*
        FROM password_reset_tokens rt
        JOIN users u ON u.user_id = rt.user_id
        WHERE rt.token = %s
        """,
        (data.token,),
    ).fetchone()
    if row is None or row["used_at"] is not None:
        raise HTTPException(status_code=400, detail="Jeton de réinitialisation invalide.")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Jeton de réinitialisation expiré.")
    if not row["is_active"]:
        raise HTTPException(status_code=400, detail="Compte inactif ou suspendu.")

    service = UserService(db)
    try:
        service._validate_password_history(row["user_id"], data.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    password_hash = hash_password(data.new_password)
    db.execute(
        """
        UPDATE users
        SET password_hash = %s, must_change_password = FALSE, failed_attempts = 0,
            locked_until = NULL, suspended_at = NULL, last_password_change_at = %s,
            updated_at = %s
        WHERE user_id = %s
        """,
        (password_hash, datetime.now(timezone.utc), datetime.now(timezone.utc), row["user_id"]),
    )
    service._add_password_history(row["user_id"], password_hash)
    service._trim_password_history(row["user_id"])
    db.execute(
        "UPDATE password_reset_tokens SET used_at = %s WHERE reset_token_id = %s",
        (datetime.now(timezone.utc), row["reset_token_id"]),
    )
    log_action(db, row["user_id"], "password_reset_link", "user", row["user_id"],
               f"Réinitialisation du mot de passe via lien pour {row['login']}")

    auth = AuthService(db)
    result = auth.authenticate_user(LoginRequest(login=row["login"], password=data.new_password, client_code=row.get("user_code")))
    if result is None:
        return {"ok": True, "message": "Mot de passe réinitialisé. Veuillez vous connecter."}
    return {"ok": True, "message": "Mot de passe réinitialisé.", **result.model_dump()}


@router.post("/logout", response_model=MessageResponse)
def logout():
    return MessageResponse(message="Déconnexion réussie.")