from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.config import get_settings
from app.core.security import create_media_token
from app.schemas.auth import UserInfo
from app.dependencies.auth import require_activated

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
    current_user: UserInfo = Depends(require_activated),
) -> MediaTokenResponse:
    """Émet un token MÉDIA court vécu, scopé à UN seul fichier.

    À utiliser pour construire les URL des balises <img>/<video> (GET /media/{path}).
    Le token est dédié : inutilisable comme token de session (typ=media), limité au
    chemin exact demandé, et expire après MEDIA_TOKEN_EXPIRE_MINUTES.
    """
    media_path = body.path.lstrip("/")
    token = create_media_token(current_user.user_id, media_path)
    return MediaTokenResponse(
        token=token,
        expires_in=settings.MEDIA_TOKEN_EXPIRE_MINUTES * 60,
        media_path=media_path,
    )