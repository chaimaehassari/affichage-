from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from psycopg import Connection

from app.core.config import get_settings
from app.core.security import create_media_token
from app.db.database import get_db
from app.schemas.auth import UserInfo
from app.dependencies.auth import get_current_user_dependency
from app.services.scope import assert_media_in_scope, client_scope, is_superadmin
from app.services.site_service import MediaService

router = APIRouter(prefix="/api/v1", tags=["Media"])

settings = get_settings()


class MediaTokenRequest(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v):
        if not v or not v.strip():
            raise ValueError("Le chemin média est obligatoire.")
        return v.strip()


class MediaTokenResponse(BaseModel):
    token: str
    expires_in: int
    media_path: str


@router.post("/media-token", response_model=MediaTokenResponse)
def issue_media_token(
    body: MediaTokenRequest,
    current_user: UserInfo = Depends(get_current_user_dependency),
    db: Connection = Depends(get_db),
) -> MediaTokenResponse:
    """Émet un token MÉDIA court vécu, scopé à UN seul fichier.

    À utiliser pour construire les URL des balises <img>/<video> (GET /media/{path}).
    Le token est dédié : inutilisable comme token de session (typ=media), limité au
    chemin exact demandé, et expire après MEDIA_TOKEN_EXPIRE_MINUTES.

    Le chemin est contrÔlé AVANT l'émission. Sans ce contrôle, la route
    signait N'IMPORTE QUEL chemin du stockage SFTP : il suffisait de connaître
    (ou de deviner) le `sftp_path` d'un média d'un autre client — devolvu par
    le listing, et souvent devinable à partir du nom de fichier — pour obtenir
    une URL signée puis télécharger le fichier via `GET /media/{path}`. Le
    token média est la seule chose qui protège cette route : c'est donc ici
    que le périmètre doit être vérifié.

    Le chemin doit se résoudre à un média du périmètre (`MediaService
    .media_id_for_path`, qui couvre aussi les pages PDF rendues). Un chemin
    inconnu est refusé : fail-closed, on ne signe pas un fichier dont on
    n'a pas établi le propriétaire. Le Super Admin garde la vue globale.
    """
    media_path = body.path.lstrip("/")

    if not is_superadmin(current_user):
        media_id = MediaService(db).media_id_for_path(media_path)
        if media_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ce fichier média n'appartient pas à votre périmètre.",
            )
        try:
            assert_media_in_scope(db, client_scope(db, current_user),
                                  current_user.user_id, media_id)
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    token = create_media_token(current_user.user_id, media_path)
    return MediaTokenResponse(
        token=token,
        expires_in=settings.MEDIA_TOKEN_EXPIRE_MINUTES * 60,
        media_path=media_path,
    )