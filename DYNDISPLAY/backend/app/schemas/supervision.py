from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

# Types de médias acceptés dans le champ `current_media` du heartbeat.
ALLOWED_MEDIA_TYPES = {"IMAGE", "VIDEO", "PDF"}


class SupervisionPostOut(BaseModel):
    post_id: int
    code: str
    name: str
    is_online: bool
    is_up_to_date: bool
    last_sync_at: str | None = None
    last_heartbeat_at: str | None = None
    display_enabled: bool
    status: str


class SupervisionSiteOut(BaseModel):
    site_id: int
    code: str
    name: str
    posts: list[SupervisionPostOut]


class PingResultOut(BaseModel):
    reachable: bool
    rtt_ms: float | None = None
    message: str


class PingBatchOut(BaseModel):
    # Clé = post_id. Un poste du périmètre sans adresse IP y figure quand
    # même (`reachable: false`) : `message` distingue alors « injoignable »
    # de « adresse non renseignée », que l'UI doit pouvoir expliquer.
    results: dict[int, PingResultOut]
    total: int
    # Postes du périmètre NON testés, le plafond de pings simultanés étant
    # atteint. > 0 doit être signalé dans la console : un poste sans
    # résultat n'est pas un poste injoignable, c'est un poste non mesuré.
    skipped: int = 0


class CurrentMediaInfo(BaseModel):
    """Média actuellement diffusé par le player, remonté via le heartbeat.

    Le champ reste optionnel : un heartbeat sans `current_media` signifie
    « rien à afficher pour l'instant » (ex. juste après démarrage) et ne lève
    jamais d'erreur.

    Règle multi-zones : si plusieurs zones sont actives simultanément, le
    player envoie le média de la zone active dont le `zone_number` est le plus
    bas. Le backend stocke la valeur et ne tranche pas.
    """

    media_id: int | None = None
    name: str | None = None
    media_type: str | None = None
    zone_number: int | None = None
    started_at: datetime | None = None

    @field_validator("media_type")
    @classmethod
    def _validate_media_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        norm = str(value).strip().upper()
        if norm not in ALLOWED_MEDIA_TYPES:
            raise ValueError(
                "Type de média invalide. Valeurs attendues : IMAGE, VIDEO, PDF."
            )
        return norm


class HeartbeatRequest(BaseModel):
    post_id: int
    current_media: CurrentMediaInfo | None = None


# États de diffusion d'un poste, tels qu'affichés par la console.
#
#   up_to_date : en ligne, et le média réellement diffusé fait partie des
#                médias affectés au poste → le poste diffuse bien ce qui est
#                programmed.
#   changed    : en ligne, mais le média diffusé N'EST PAS dans les médias
#                affectés → le poste affiche encore l'ancien contenu (la
#                synchronisation n'a pas encore été appliquée par le player).
#   no_media   : en ligne, mais aucun média affecté au poste : il n'y a rien à
#                comparer.
#   unknown    : en ligne, mais le player n'a rien remonté (jamais de média
#                signalé depuis le dernier démarrage).
#   offline    : poste hors ligne (dernier heartbeat au-delà du seuil) : son
#                état de diffusion est par définition inconnu.
DIFFUSION_STATES = {"up_to_date", "changed", "no_media", "unknown", "offline"}


class DiffusionReportPostOut(BaseModel):
    post_id: int
    post_code: str
    post_name: str
    site_id: int
    site_name: str
    # Client propriétaire du poste : indispensable pour un admin de groupe,
    # dont le rapport couvre plusieurs clients à la fois.
    client_code: str | None = None
    client_name: str | None = None
    is_online: bool
    current_media_name: str | None = None
    current_media_type: str | None = None
    current_media_started_at: str | None = None
    last_heartbeat_at: str | None = None
    last_sync_at: str | None = None
    thumbnail_path: str | None = None
    # Ce qui est PROGRAMMÉ sur le poste (affectations de zone actives).
    assigned_media_names: list[str] = []
    assigned_media_count: int = 0
    # Verdict « à jour » / « pas encore changé » (voir DIFFUSION_STATES).
    diffusion_state: Literal[
        "up_to_date", "changed", "no_media", "unknown", "offline"
    ] = "unknown"
    is_up_to_date: bool = False


class DiffusionReportOut(BaseModel):
    posts: list[DiffusionReportPostOut]
    total: int