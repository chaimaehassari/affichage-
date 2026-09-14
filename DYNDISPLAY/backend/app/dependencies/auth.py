from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from app.db.database import get_db
from app.core.security import decode_access_token
from app.schemas.auth import UserInfo
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer()


def get_current_user_dependency(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Connection = Depends(get_db),
) -> UserInfo:
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
        )

    user_id = int(payload.get("sub"))
    service = AuthService(db)
    user = service.get_current_user(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable ou désactivé.",
        )

    return user


ADMIN_PROFILE_NAME = "Administrateur"


def is_admin_user(current_user: UserInfo) -> bool:
    return current_user.profile_name == ADMIN_PROFILE_NAME


def require_permission(permission_code: str):
    def dependency(
        current_user: UserInfo = Depends(get_current_user_dependency),
    ) -> UserInfo:
        if is_admin_user(current_user):
            return current_user

        perm = next(
            (p for p in current_user.permissions if p.code == permission_code),
            None,
        )
        if perm is None or not perm.can_view:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission insuffisante.",
            )
        return current_user
    return dependency


def require_activated(
    current_user: UserInfo = Depends(get_current_user_dependency),
) -> UserInfo:
    """Bloque les comptes clients non activés (sauf administrateur).

    Un compte en attente d'activation ne peut toucher aucune donnée :
    il doit d'abord saisir son code de sérialisation (POST /auth/activate,
    qui vit dans le routeur auth, non soumis à ce garde-fou).
    """
    if not is_admin_user(current_user) and not current_user.is_activated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte doit être activé par un code de sérialisation.",
        )
    return current_user