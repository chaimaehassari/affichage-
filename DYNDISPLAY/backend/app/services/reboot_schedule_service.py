"""Programmation des redémarrages automatiques des postes.

Deux mécanismes INDÉPENDANTS cohabitent sur un même poste :

  * le récurrent (migration 021) : ``reboot_enabled`` / ``reboot_time`` /
    ``next_reboot_at`` — une heure répétée chaque jour ;
  * le ponctuel (migration 022) : ``reboot_once_at`` — UN instant, consommé
    puis purgé.

Conventions :
  * ``reboot_time`` est exprimé au format "HH:MM" dans le fuseau de
    l'application (``APP_TIMEZONE``) et mémorisé en colonne TIME.
  * ``next_reboot_at`` est la prochaine échéance en UTC (TIMESTAMPTZ),
    recalculée à chaque écriture ET en lecture si l'échéance est dépassée
    (échéance saine → jour suivant).
  * ``reboot_once_at`` est un instant absolu, stocké en UTC. Il est REJETÉ à
    l'écriture s'il est déjà passé (pas de rattrapage) et PURGÉ à la lecture
    dès qu'il est dépassé d'une marge de grâce.
  * « Désactiver » (reboot_enabled = FALSE) conserve reboot_time intact et
    ne touche pas reboot_once_at.
"""

import re
from datetime import datetime, timedelta, timezone

from psycopg import Connection

from app.core.times import get_app_tz, now_app, to_utc

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Instant ISO 8601 accepté pour reboot_once_at : "YYYY-MM-DDTHH:MM" (sortie
# d'un <input type="datetime-local">), avec secondes et/ou décalage facultatifs.
ONCE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)

# Marge de grâce avant purge de reboot_once_at (minutes).
#
# Justification : le player n'agit qu'au chargement d'une config, donc après
# démarrage d'Electron + lecture du config.json. 10 min couvre largement
# reprise depuis veille, boot, démarrage du player et premier poll FTP, tout en
# restant une marge raisonnable face à la fenêtre de 5 min du récurrent
# (REBOOT_WINDOW_MIN côté player) : au-delà, une demande manquée ne reste pas
# armée. Passed time = le reboot a eu lieu (ou la box était éteinte) : on
# purge dans les deux cas, ce qui est le comportement « no catch-up » voulu.
REBOOT_ONCE_GRACE_MIN = 10

ONCE_FORMAT_ERROR = (
    'Le format de la date de redémarrage ponctuel doit être "YYYY-MM-DDTHH:MM".'
)
ONCE_PAST_ERROR = "Le redémarrage ponctuel doit être programmé dans le futur."


def validate_reboot_time(value) -> str | None:
    """Normalise une heure "HH:MM" ; None si vide ; ValueError si invalide."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if not TIME_RE.match(v):
        raise ValueError('Le format de l\'heure de redémarrage doit être "HH:MM".')
    return v


def check_reboot_once_format(value) -> None:
    """Valide le FORMAT d'un instant de redémarrage ponctuel.

    Lève ValueError avec un message explicite (→ 422 FastAPI). La comparaison
    au futur est faite séparément, sur le datetime déjà parsé, par
    ``check_reboot_once_future``.
    """
    if value is None:
        return
    if isinstance(value, datetime):
        return
    v = str(value).strip()
    if not v:
        return
    if not ONCE_RE.match(v):
        raise ValueError(ONCE_FORMAT_ERROR)
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(ONCE_FORMAT_ERROR)


def check_reboot_once_future(dt: datetime | None) -> None:
    """Lève ValueError si l'instant est déjà passé (pas de rattrapage)."""
    if dt is None:
        return
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=get_app_tz())
    if aware <= now_app():
        raise ValueError(ONCE_PAST_ERROR)


def compute_next_reboot_at(reboot_time: str) -> datetime:
    """Prochaine échéance strictement future de reboot (UTC aware).

    Dans le fuseau de l'application : aujourd'hui à `reboot_time` si pas déjà
    passé, sinon demain à la même heure. L'échéance est ensuite convertie en
    UTC pour le stockage TIMESTAMPTZ.
    """
    hour, minute = (int(p) for p in reboot_time.split(":"))
    now = now_app()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return to_utc(target)


def time_column_str(value) -> str | None:
    """Sérialise une valeur TIME (datetime.time) en "HH:MM"."""
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    if isinstance(value, str) and TIME_RE.match(value.strip()):
        return value.strip()
    return None


def refresh_next_reboot_at(conn: Connection, post_id: int) -> dict:
    """Garde next_reboot_at cohérent et renvoie le couple reboot à jour.

    - reboot activé avec heure : l'échéance est recalculée si absente ou
      dépassée (après un reboot effectif, on passe silencieusement au jour
      suivant — jamais de boucle de redémarrage en rafale).
    - reboot désactivé : l'échéance est remise à NULL (reboot_time conservé).
    """
    post = conn.execute(
        """
        SELECT reboot_enabled, reboot_time, next_reboot_at
        FROM posts
        WHERE post_id = %s
        """,
        (post_id,),
    ).fetchone()
    if not post:
        return {"reboot_enabled": False, "reboot_time": None, "next_reboot_at": None}

    enabled = bool(post["reboot_enabled"])
    reboot_time = time_column_str(post.get("reboot_time"))
    next_reboot_at = post.get("next_reboot_at")
    dirty = False

    if enabled and reboot_time:
        if next_reboot_at is None or next_reboot_at <= datetime.now(timezone.utc):
            next_reboot_at = compute_next_reboot_at(reboot_time)
            dirty = True
    elif next_reboot_at is not None:
        next_reboot_at = None
        dirty = True

    if dirty:
        conn.execute(
            "UPDATE posts SET next_reboot_at = %s, updated_at = %s WHERE post_id = %s",
            (next_reboot_at, datetime.now(timezone.utc), post_id),
        )

    return {
        "reboot_enabled": enabled,
        "reboot_time": reboot_time,
        "next_reboot_at": next_reboot_at.isoformat() if next_reboot_at else None,
    }


def once_deadline(reboot_once_at: datetime) -> datetime:
    """Instant de purge de reboot_once_at : échéance + marge de grâce."""
    return to_utc(reboot_once_at) + timedelta(minutes=REBOOT_ONCE_GRACE_MIN)


def refresh_reboot_once_at(conn: Connection, post_id: int) -> dict:
    """Purger reboot_once_at si l'échéance est dépassée (marge de grâce incluse).

    Déduction serveur pure, sur le modèle de ``refresh_next_reboot_at`` :
    aucune confirmation n'est attendue du player. Dès que
    ``now() >= reboot_once_at + REBOOT_ONCE_GRACE_MIN``, le champ est remis à
    NULL — que le reboot ait eu lieu (box allumée) ou non (box éteinte, la
    demande est perdue : c'est le « no catch-up » voulu pour un one-shot).

    Ne touche ni au récurrent ni au reste de la configuration du poste.
    """
    post = conn.execute(
        "SELECT reboot_once_at FROM posts WHERE post_id = %s",
        (post_id,),
    ).fetchone()
    if not post:
        return {"reboot_once_at": None}

    once_at = post.get("reboot_once_at")
    if once_at is None:
        return {"reboot_once_at": None}

    if datetime.now(timezone.utc) < once_deadline(once_at):
        return {"reboot_once_at": once_at.isoformat()}

    conn.execute(
        "UPDATE posts SET reboot_once_at = NULL, updated_at = %s WHERE post_id = %s",
        (datetime.now(timezone.utc), post_id),
    )
    return {"reboot_once_at": None}