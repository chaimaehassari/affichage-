import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import get_settings
from app.db.database import init_db, close_db
from app.dependencies.auth import require_activated
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.sites import router as sites_router
from app.api.routes.layouts import router as layouts_router
from app.api.routes.configuration import router as configuration_router
from app.api.routes.sync import router as sync_router
from app.api.routes.supervision import router as supervision_router
from app.api.routes.settings import router as settings_router
from app.api.routes.audit import router as audit_router
from app.sftp.client import SFTPClient

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
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
app.include_router(users_router, dependencies=[Depends(require_activated)])
app.include_router(sites_router, dependencies=[Depends(require_activated)])
app.include_router(layouts_router, dependencies=[Depends(require_activated)])
app.include_router(configuration_router, dependencies=[Depends(require_activated)])
app.include_router(sync_router, dependencies=[Depends(require_activated)])
app.include_router(supervision_router)
app.include_router(settings_router, dependencies=[Depends(require_activated)])
app.include_router(audit_router, dependencies=[Depends(require_activated)])


def _media_stream(remote_path: str):
    with SFTPClient() as sftp:
        with sftp.open_remote(remote_path, "rb") as f:
            while chunk := f.read(256 * 1024):
                yield chunk


@app.get("/media/{path:path}")
def serve_media(path: str):
    clean_path = path.lstrip("/")
    root = settings.SFTP_ROOT_PATH.rstrip("/")
    remote_path = f"{root}/{clean_path}"
    with SFTPClient() as probe:
        if not probe.exists(remote_path):
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
    media_type = mimetypes.guess_type(clean_path)[0] or "application/octet-stream"
    return StreamingResponse(_media_stream(remote_path), media_type=media_type)


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