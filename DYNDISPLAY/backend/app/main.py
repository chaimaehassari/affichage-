import asyncio
import logging
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import get_settings
from app.db.database import init_db, close_db
from app.dependencies.auth import require_media_access
from app.schemas.auth import UserInfo
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.admins import router as admins_router
from app.api.routes.sites import router as sites_router
from app.api.routes.layouts import router as layouts_router
from app.api.routes.configuration import router as configuration_router
from app.api.routes.sync import router as sync_router
from app.api.routes.supervision import router as supervision_router
from app.api.routes.settings import router as settings_router
from app.api.routes.audit import router as audit_router
from app.api.routes.media import router as media_router
from app.services.media_storage import (
    InvalidMediaPath,
    MediaStore,
    StorageUnavailable,
    get_media_store,
    is_sftp_configured,
    normalize_relative_path,
)

settings = get_settings()
logger = logging.getLogger("dyndisplay.startup")


class _MediaNotFound(Exception):
    """Le fichier a disparu entre la vérification d'existence et la lecture.

Interne au streaming : le statut 200 est déjà parti, on ne peut plus rien
    changer. Les erreurs de chemin et de stockage, elles, sont levées avant
    le retour de la route et gardent leur vrai code.
    """


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # Le backend de stockage des médias est choisi au démarrage et non à
    # chaque requête : un serveur qui stocke sur le disque local parce que
    # SFTP n'est pas configuré doit le dire, sinon la seule trace est un 503
    # « Connexion SFTP impossible » envoyé à l'utilisateur, qui suggère un
    # incident réseau alors que personne n'a jamais demandé de SFTP.
    if is_sftp_configured():
        logger.info(
            "Stockage des medias : SFTP %s, racine %s.",
            settings.SFTP_HOST, settings.SFTP_ROOT_PATH,
        )
    else:
        manquantes = [
            nom for nom in ("SFTP_HOST", "SFTP_USERNAME", "SFTP_ROOT_PATH")
            if not (getattr(settings, nom, "") or "").strip()
        ]
        logger.info(
            "Stockage des medias : dossier local %s (%s non renseigne%s : "
            "la synchronisation vers les players reste inactive).",
            settings.MEDIA_ROOT,
            ", ".join(manquantes),
            "s" if len(manquantes) > 1 else "",
        )

    try:
        yield
    finally:
        close_db()


app = FastAPI(
    title="DYNDISPLAY API",
    description="Digital Signage Management Platform",
    version="0.5.0",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admins_router)
app.include_router(sites_router)
app.include_router(layouts_router)
app.include_router(configuration_router)
app.include_router(sync_router)
app.include_router(supervision_router)
app.include_router(settings_router)
app.include_router(audit_router)
app.include_router(media_router)


def _media_stream(store: MediaStore, relative_path: str):
    yield from store.stream(relative_path)


@app.get("/media/{path:path}")
def serve_media(
    path: str,
    current_user: UserInfo = Depends(require_media_access),
):
    """Sert un média depuis le stockage configuré, pour les aperçus web.

    Le stockage est choisi par `get_media_store()` : SFTP s'il est configuré,
    MEDIA_ROOT sinon. Une installation sans SFTP pouvait donc importer un
    média (qui atterrissait sur le disque) sans jamais pouvoir l'afficher,
    parce que cette route lisait SFTP inconditionnellement.

    PROTÉGÉ PAR JWT MÉDIA : la route exige un token MÉDIA dédié (en-tête
    Authorization OU paramètre `token` — requis pour les balises <img>/<video>).
    Justification de ne PAS l'exposer publiquement :
      - les players (Android, Windows) lisent directement le partage SFTP et
        n'utilisent JAMAIS cette route HTTP — aucun usage légitime public ;
      - les seuls consommateurs sont les écrans de prévisualisation du
        frontend (sessions authentifiées) ;
      - le token en query est un token média court vécu
        (< MEDIA_TOKEN_EXPIRE_MINUTES), scopé au chemin exact du fichier,
        inutilisable comme token de session (typ=media), distinct du JWT
        ACCESS de l'API pour limiter l'exposition en cas de fuite dans les
        logs d'accès / URL.
    """
    try:
        relative_path = normalize_relative_path(path)
    except InvalidMediaPath as e:
        raise HTTPException(status_code=400, detail=str(e))

    media_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"

    def stream():
        try:
            with get_media_store() as store:
                if not store.exists(relative_path):
                    raise _MediaNotFound()
                yield from _media_stream(store, relative_path)
        except _MediaNotFound:
            # Le client a déjà reçu le 200 et l'en-tête Content-Type quand le
            # générateur démarre : un 404 n'est plus possible, on coupe la
            # réponse. C'est le seul trou possible entre `exists()` ci-dessus
            # et la lecture — le fichier a été supprimé entre les deux.
            logger.warning("Média disparu pendant le streaming : %s", relative_path)
            return
        except StorageUnavailable as e:
            logger.error("Stockage des médias indisponible (%s) : %s", relative_path, e)
            return

    # `exists()` est fait AVANT le retour de la route, donc un fichier absent
    # produit un vrai 404. Il est répété dans le générateur parce que la
    # connexion s'ouvre au moment du streaming : on veut la même garantie
    # qu'avec SFTP, où `probe` ouvrait une session juste pour vérifier.
    try:
        with get_media_store() as probe:
            if not probe.exists(relative_path):
                raise HTTPException(status_code=404, detail="Fichier introuvable.")
    except StorageUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Erreur de stockage des médias : {e}")

    return StreamingResponse(
        stream(),
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/")
def root():
    if settings.UI_DIST_PATH and os.path.isdir(settings.UI_DIST_PATH):
        return FileResponse(os.path.join(settings.UI_DIST_PATH, "index.html"))
    return {"message": "DYNDISPLAY API is running"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _resolve_ui_path(full_path: str):
    """Résout un chemin demandé dans le frontend compilé (fichier ou index.html)."""
    if not settings.UI_DIST_PATH or not os.path.isdir(settings.UI_DIST_PATH):
        return None
    if full_path:
        candidate = os.path.join(settings.UI_DIST_PATH, full_path)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(settings.UI_DIST_PATH, "index.html")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Sert le frontend compilé en dernier (assets + fallback SPA).
    Enregistré après toutes les routes API : celles-ci restent prioritaires."""
    if full_path.startswith(("api/", "media/", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not Found")
    file_path = _resolve_ui_path(full_path)
    if file_path:
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Not Found")