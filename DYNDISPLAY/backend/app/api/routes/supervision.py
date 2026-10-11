from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import require_permission
from app.schemas.supervision import (
    DiffusionReportOut,
    HeartbeatRequest,
    PingBatchOut,
)
from app.services.scope import assert_post_scope
from app.services.supervision_service import SupervisionService

router = APIRouter(prefix="/api/v1", tags=["Supervision"])


@router.get("/supervision")
def get_supervision(
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    service = SupervisionService(db)
    return service.get_supervision_data(current_user)


@router.post("/posts/heartbeat")
def send_heartbeat(
    payload: HeartbeatRequest,
    db: Connection = Depends(get_db),
):
    service = SupervisionService(db)
    ok = service.send_heartbeat(payload.post_id, payload.current_media)
    if not ok:
        raise HTTPException(status_code=404, detail="Poste introuvable.")
    return {"message": "Heartbeat reçu."}


@router.post("/posts/{post_id}/ping")
def ping_post(
    post_id: int,
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    try:
        assert_post_scope(db, current_user, post_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    service = SupervisionService(db)
    return service.ping_post(post_id)


@router.post("/supervision/ping", response_model=PingBatchOut)
def ping_all_posts(
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    """Ping ICMP de tous les postes du périmètre, en parallèle.

    Endpoint utilisé par la console pour un ping automatique à chaque
    rechargement / rafraîchissement de la page Supervision.

    Un seul appel au lieu d'un appel par poste : le ping étant bloquant
    (jusqu'à `PING_TIMEOUT_SECONDS` côté serveur), N requêtes simultanées
    satureraient le pool de connexions PostgreSQL et le rechargement de la
    page prendrait N × le timeout.

    Le périmètre provient exclusivement de la session — aucun `post_id` n'est
    accepté en paramètre — exactement comme pour le rapport de diffusion.
    """
    service = SupervisionService(db)
    results, skipped = service.ping_all_posts(current_user)
    return PingBatchOut(results=results, total=len(results), skipped=skipped)


def _diffusion_report(
    db: Connection,
    current_user,
    post_id: int | None,
) -> DiffusionReportOut:
    service = SupervisionService(db)
    try:
        items = service.get_diffusion_report(current_user, post_id)
    except PermissionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return DiffusionReportOut(posts=items, total=len(items))


@router.get("/supervision/diffusion-report", response_model=DiffusionReportOut)
def get_diffusion_report_group(
    post_id: int | None = Query(
        default=None,
        description=(
            "Filtre optionnel sur un poste précis. L'appartenance au périmètre "
            "est vérifiée côté backend : un poste d'un autre client n'est jamais "
            "retourné (404, aucune donnée divulguée)."
        ),
    ),
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    """Rapport de diffusion — un poste par ligne, sur TOUS les clients du périmètre.

    Le périmètre est déduit exclusivement de la session (jamais d'un paramètre) :

      * Super Admin     → tous les clients ;
      * Admin de groupe → tous les clients affectés via `admin_clients` ;
      * Compte client   → son seul code client.

    Un poste = une ligne, avec le client, le média réellement diffusé et son
    « depuis quand », l'état en ligne/hors ligne, et le verdict
    « à jour » / « pas encore changé » (médias affectés comparés au média
    réellement diffusé).
    """
    return _diffusion_report(db, current_user, post_id)


@router.get("/clients/me/posts/diffusion-report", response_model=DiffusionReportOut)
def get_diffusion_report(
    post_id: int | None = Query(
        default=None,
        description=(
            "Filtre optionnel sur un poste précis. L'appartenance au client est "
            "vérifiée côté backend : un poste d'un autre client n'est jamais "
            "retourné (404, aucune donnée divulguée)."
        ),
    ),
    current_user=Depends(require_permission("menu_config")),
    db: Connection = Depends(get_db),
):
    """Ancienne URL du rapport de diffusion, conservée pour compatibilité.

    Même implémentation que `/supervision/diffusion-report` : le libellé « me »
    était trompeur, un admin de groupe n'a pas un client unique mais tous les
    clients de son groupe. La nouvelle URL est celle qu'utilise la console ;
    celle-ci est gardée pour ne pas casser les appelsants existants.
    """
    return _diffusion_report(db, current_user, post_id)