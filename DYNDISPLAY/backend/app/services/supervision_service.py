import logging
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from psycopg import Connection

from app.schemas.supervision import CurrentMediaInfo
from app.services.scope import (
    is_superadmin,
    client_scope,
    scope_as_list,
    scope_sql,
)

logger = logging.getLogger(__name__)

HEARTBEAT_OFFLINE_THRESHOLD_SECONDS = 90
PING_TIMEOUT_SECONDS = 5
# Nombre de `ping` simultanés dans le lot. Au-delà, on sature la machine
# pour un gain nul : un `ping` bloque son thread jusqu'a PING_TIMEOUT_SECONDS,
# donc 8 postes en parallèle attendent ~5 s comme 50.
PING_BATCH_MAX_WORKERS = 8
# Nombre maximal de `ping` RÉELS lancés par un lot. Chaque ping bloquerait
# jusqu'a PING_TIMEOUT_SECONDS : sans plafond, un parc entier hors ligne
# immobiliserait la requête pendant (N / workers) × timeout, et la page
# Supervision resterait figée. Les postes sans IP ne consomment aucun ping
# (cf. `ping_all_posts`) et ne sont donc pas concernés par ce plafond.
PING_BATCH_MAX_PINGS = 60


class SupervisionService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def get_supervision_data(self, user) -> list[dict]:
        """Postes Supervision du périmètre de l'utilisateur.

        Le périmètre vient de `client_scope()`, la source de vérité unique :
        cette méthode NE REDÉFINIT PAS sa propre règle. Elle le faisait, et
        comparait `users.user_code` (le code de connexion du compte) à
        `sites.client_code` (le code du client) — deux espaces différents. Un
        profil 2/3 obtenait donc une liste VIDE alors que le rapport de
        diffusion, lui, passait par `client_scope()` et voyait ses 53 postes.
        Même session, deux périmètres. `ping_all_posts` en héritait : aucun
        poste à pinger.
        """
        if is_superadmin(user):
            return self._all_data()
        return self._scoped_data(user, client_scope(self.conn, user))

    def _all_data(self) -> list[dict]:
        sites = self.conn.execute(
            "SELECT * FROM sites WHERE is_active = TRUE ORDER BY name"
        ).fetchall()
        # Posts de TOUS les sites en une requête : une requête par site
        # rendait le temps d'affichage linéaire en nombre de sites.
        posts_by_site = self._posts_by_site([s["site_id"] for s in sites])
        return [
            self._site_out(site, posts_by_site.get(site["site_id"], []))
            for site in sites
        ]

    def _posts_by_site(self, site_ids: list[int]) -> dict[int, list[dict]]:
        """Posts actifs de plusieurs sites, regroupés par site (1 requête)."""
        if not site_ids:
            return {}
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE site_id = ANY(%s) AND is_active = TRUE ORDER BY code",
            (site_ids,),
        ).fetchall()
        grouped: dict[int, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["site_id"], []).append(row)
        return grouped

    def _display_enabled_by_post(self, post_ids: list[int]) -> dict[int, bool]:
        """`display_enabled` de plusieurs postes en une requête.

        Indispensable au chargement de la page Supervision : cette colonne
        était lue par une requête **par poste**, soit 1 900 allers-retours
        sur un parc comparable — plusieurs secondes avant même le moindre
        rendu, et le double pour le ping automatique (cf. `ping_all_posts`).
        """
        if not post_ids:
            return {}
        rows = self.conn.execute(
            "SELECT post_id, display_enabled FROM post_configurations WHERE post_id = ANY(%s)",
            (post_ids,),
        ).fetchall()
        return {r["post_id"]: r["display_enabled"] for r in rows}

    def _scoped_data(self, user, codes) -> list[dict]:
        """Postes des clients de `codes` + ceux d'un groupe autorisé à l'user.

        `codes` est toujours produit par `client_scope()` : `None` signifie
        « pas de filtre » (Super Admin) et y renvoie la vue globale.
        """
        if codes is None:
            return self._all_data()
        effective = scope_as_list(codes)
        if not effective:
            return []
        rows = self.conn.execute(
            """
            SELECT s.site_id, s.code AS site_code, s.name AS site_name,
                   p.post_id, p.code, p.name,
                   p.is_online, p.is_up_to_date, p.last_sync_at, p.last_heartbeat_at,
                   pc.display_enabled
            FROM posts p
            JOIN sites s ON s.site_id = p.site_id AND s.is_active = TRUE
            LEFT JOIN post_configurations pc ON pc.post_id = p.post_id
            LEFT JOIN screen_group_posts sgp ON sgp.post_id = p.post_id
            LEFT JOIN user_group_access uga
                   ON uga.group_id = sgp.group_id AND uga.user_id = %s AND uga.is_allowed = TRUE
            WHERE p.is_active = TRUE
              AND (s.client_code = ANY(%s) OR uga.user_group_access_id IS NOT NULL)
            ORDER BY s.site_id, s.name, p.code
            """,
            (user.user_id, effective),
        ).fetchall()

        result = []
        site_by_id = {}
        order: list[int] = []
        for r in rows:
            site_id = r["site_id"]
            if site_id not in site_by_id:
                site_by_id[site_id] = {
                    "site_id": site_id,
                    "code": r["site_code"],
                    "name": r["site_name"],
                    "posts": [],
                }
                order.append(site_id)
            posts_list = site_by_id[site_id]["posts"]
            if any(x["post_id"] == r["post_id"] for x in posts_list):
                continue
            # `pc.display_enabled` vient de la requête ci-dessus. La colonne
            # est NOT NULL, donc NULL = aucune ligne `post_configurations`
            # (LEFT JOIN sans correspondance) → l'affichage est actif par
            # défaut, comme le faisait l'ancienne lecture par poste.
            enabled = r["display_enabled"]
            posts_list.append(
                self._post_out(r, True if enabled is None else enabled)
            )
        for site_id in order:
            result.append(site_by_id[site_id])
        return result

    def _site_out(self, site, posts: list[dict]) -> dict:
        display_enabled = self._display_enabled_by_post([p["post_id"] for p in posts])
        return {
            "site_id": site["site_id"],
            "code": site["code"],
            "name": site["name"],
            "posts": [
                self._post_out(p, display_enabled.get(p["post_id"], True))
                for p in posts
            ],
        }

    def _post_out(self, post: dict, display_enabled: bool = True) -> dict:
        return {
            "post_id": post["post_id"],
            "code": post["code"],
            "name": post["name"],
            "is_online": post["is_online"],
            "is_up_to_date": post["is_up_to_date"],
            "last_sync_at": post["last_sync_at"].isoformat() if post["last_sync_at"] else None,
            "last_heartbeat_at": post["last_heartbeat_at"].isoformat() if post["last_heartbeat_at"] else None,
            "display_enabled": display_enabled,
            "status": self._compute_status(post),
        }

    def _compute_status(self, post: dict) -> str:
        offline_threshold = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_OFFLINE_THRESHOLD_SECONDS)
        is_online = post["last_heartbeat_at"] is not None and post["last_heartbeat_at"] >= offline_threshold
        if not is_online:
            return "offline"
        if not post["last_sync_at"]:
            return "never_synced"
        if post["is_up_to_date"]:
            return "online"
        return "outdated"

    def send_heartbeat(
        self,
        post_id: int,
        current_media: CurrentMediaInfo | None = None,
    ) -> bool:
        """Enregistre un heartbeat de player.

        Le champ `current_media` est optionnel :
        - absent / None → « rien à afficher pour l'instant », les colonnes
          current_media_* du poste sont remises à NULL (l'état est écrasé à
          chaque heartbeat reçu) ;
        - présent → le média en cours de diffusion est enregistré. `started_at`
          est normalisé en UTC avant stockage (TIMESTAMPTZ).
        """
        post = self.conn.execute(
            "SELECT post_id FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            return False
        self.conn.execute(
            """
            UPDATE posts
            SET is_online = TRUE,
                last_heartbeat_at = %s,
                current_media_id = %s,
                current_media_name = %s,
                current_media_type = %s,
                current_media_started_at = %s
            WHERE post_id = %s
            """,
            (
                datetime.now(timezone.utc),
                current_media.media_id if current_media is not None else None,
                (current_media.name or None) if current_media is not None else None,
                current_media.media_type if current_media is not None else None,
                self._as_utc(current_media.started_at) if current_media is not None else None,
                post_id,
            ),
        )
        return True

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        """Normalise une datetime en UTC (naïf = supposé UTC)."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    # -----------------------------------------------------------------------
    # Rapport de diffusion — GET /supervision/diffusion-report
    #                  (alias historique : /clients/me/posts/diffusion-report)
    # -----------------------------------------------------------------------

    def get_diffusion_report(self, user, post_id: int | None = None) -> list[dict]:
        """Retourne le rapport de diffusion des postes du périmètre de l'utilisateur.

        Le périmètre est déduit de la session (`client_scope`) et JAMAIS d'un
        paramètre de l'appelant :

          * Super Admin        → aucun filtre (tous les clients) ;
          * Admin de groupe    → les clients affectés via `admin_clients`
                                (TOUS ses clients, pas un seul) ;
          * Compte client      → son seul code client.

        Deux admins de groupes différents ne se voient donc jamais : c'est le
        même mécanisme de scope que le reste de l'application, et l'isolation
        reste appliquée exclusivement côté SQL. Même si un `post_id` d'un autre
        client est forcé, le poste sort du périmètre → 404, aucune donnée.

        `is_online` est recalculé par rapport au seuil de heartbeat (90 s),
        indépendamment du flag temps réel de la table. Un poste hors ligne ne
        divulgue aucun `current_media_*` obsolète (valeurs mises à None) et son
        état de diffusion vaut `offline`.
        """
        scope = client_scope(self.conn, user)
        # La requête joint `sites` ET `media` : la colonne doit être qualifiée,
        # sinon `client_code` est ambigu (sites.client_code / media.client_code).
        scope_frag, scope_params = scope_sql(scope, column="s.client_code")
        media_frag, media_params = scope_sql(scope, column="m.client_code")

        sql = f"""
            SELECT p.post_id, p.code AS post_code, p.name AS post_name,
                   p.site_id, s.name AS site_name, s.client_code AS site_client_code,
                   c.nom_client AS client_name,
                   p.current_media_id, p.current_media_name,
                   p.current_media_type, p.current_media_started_at,
                   p.last_heartbeat_at, p.last_sync_at, p.is_up_to_date,
                   m.sftp_path AS media_sftp_path
            FROM posts p
            JOIN sites s ON s.site_id = p.site_id AND s.is_active = TRUE
            LEFT JOIN clients c ON c.code_client = s.client_code
            LEFT JOIN media m ON m.media_id = p.current_media_id {media_frag}
            WHERE p.is_active = TRUE {scope_frag}
        """
        params: list = list(media_params) + list(scope_params)
        if post_id is not None:
            sql += " AND p.post_id = %s"
            params.append(post_id)
        sql += " ORDER BY s.client_code, s.name, p.code"

        rows = self.conn.execute(sql, params).fetchall()
        if post_id is not None and not rows:
            raise PermissionError("Vous n'êtes pas autorisé à accéder à ce poste.")

        assigned = self._assigned_media_by_post([r["post_id"] for r in rows])
        return [self._report_post_out(r, assigned.get(r["post_id"], [])) for r in rows]

    def _assigned_media_by_post(self, post_ids: list[int]) -> dict[int, list[dict]]:
        """Médias affectés aux zones des postes donnés : {post_id: [média, ...]}.

        Une seule requête pour tous les postes du rapport (pas de N+1) et
        aucune jointure sur `media.client_code` : un média affecté l'est par
        l'intermédiaire de son poste, donc filtrer par client ici exclurait à
        tort des médias partagés. Le périmètre, lui, est déjà garanti en amont
        par la requête principale.
        """
        if not post_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT zm.post_id, m.media_id, m.name
            FROM zone_media zm
            JOIN media m ON m.media_id = zm.media_id
            WHERE zm.post_id = ANY(%s) AND zm.is_active = TRUE
            ORDER BY zm.post_id, zm.zone_number, zm.display_order
            """,
            (post_ids,),
        ).fetchall()
        grouped: dict[int, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["post_id"], []).append(
                {"media_id": row["media_id"], "name": row["name"]}
            )
        return grouped

    @staticmethod
    def _diffusion_state(is_online: bool, current_media_id, assigned: list[dict]) -> str:
        """Verdict de diffusion, comparant l'affectation au média réellement diffusé.

        L'identifiant est comparé à l'identifiant, jamais les noms : deux
        médias peuvent porter le même libellé.
        """
        if not is_online:
            return "offline"
        if not assigned:
            return "no_media"
        if current_media_id is None:
            return "unknown"
        assigned_ids = {a["media_id"] for a in assigned}
        return "up_to_date" if current_media_id in assigned_ids else "changed"

    def _report_post_out(self, row: dict, assigned: list[dict] | None = None) -> dict:
        assigned = assigned or []
        offline_threshold = datetime.now(timezone.utc) - timedelta(
            seconds=HEARTBEAT_OFFLINE_THRESHOLD_SECONDS
        )
        is_online = (
            row["last_heartbeat_at"] is not None
            and row["last_heartbeat_at"] >= offline_threshold
        )
        state = self._diffusion_state(is_online, row["current_media_id"], assigned)
        return {
            "post_id": row["post_id"],
            "post_code": row["post_code"],
            "post_name": row["post_name"],
            "site_id": row["site_id"],
            "site_name": row["site_name"],
            "client_code": row.get("site_client_code"),
            "client_name": row.get("client_name"),
            "is_online": is_online,
            "current_media_name": row["current_media_name"] if is_online else None,
            "current_media_type": row["current_media_type"] if is_online else None,
            "current_media_started_at": (
                row["current_media_started_at"].isoformat()
                if is_online and row["current_media_started_at"]
                else None
            ),
            "last_heartbeat_at": (
                row["last_heartbeat_at"].isoformat()
                if row["last_heartbeat_at"]
                else None
            ),
            "last_sync_at": (
                row["last_sync_at"].isoformat() if row["last_sync_at"] else None
            ),
            "thumbnail_path": self._thumbnail_path_for(row) if is_online else None,
            "assigned_media_names": [a["name"] for a in assigned],
            "assigned_media_count": len(assigned),
            "diffusion_state": state,
            "is_up_to_date": state == "up_to_date",
        }

    @staticmethod
    def _thumbnail_path_for(row: dict) -> str | None:
        """Chemin relatif de la miniature à afficher (ou None).

        - IMAGE → chemin du média lui-même (`sftp_path`).
        - PDF → première page rendue à l'upload (convention `pdfs/<ts>_page_1.png`).
        - VIDEO → aucune miniature (None).
        """
        media_type = row["current_media_type"]
        sftp_path = row["media_sftp_path"]
        if not media_type or not sftp_path:
            return None
        if media_type == "IMAGE":
            return sftp_path
        if media_type == "PDF":
            return SupervisionService._pdf_page1_path(sftp_path)
        return None

    @staticmethod
    def _pdf_page1_path(sftp_path: str) -> str | None:
        """Chemin de la page 1 rendue d'un PDF, dérivé de son `sftp_path`.

        Convention d'upload : `pdfs/<timestamp>_<nom>.pdf` → pages rendues
        `pdfs/<timestamp>_page_<n>.png`.
        """
        base = sftp_path.rsplit("/", 1)[-1]
        match = re.match(r"^(\d+)_.*\.pdf$", base, re.IGNORECASE)
        if not match:
            return None
        return f"pdfs/{match.group(1)}_page_1.png"

    def ping_post(self, post_id: int) -> dict:
        """Ping ICMP réel vers l'adresse IP d'UN poste (commande ping système).

        Retourne la joignabilité et la latence (RTT en millisecondes) mesurée.
        Le travail réseau est délégué à `_ping_host`, sans accès à la base.
        """
        post = self.conn.execute(
            "SELECT post_id, ip_address FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            return {"reachable": False, "rtt_ms": None, "message": "Poste introuvable."}
        return self._ping_host(post["ip_address"])

    def ping_all_posts(self, user) -> tuple[dict[int, dict], int]:
        """Ping ICMP de TOUS les postes du périmètre, en parallèle.

        Utilisé par la console pour un ping automatique à chaque
        rafraîchissement de la page Supervision.

        Renvoie `(résultats, nombre_de_postes_non_pingés)`.

        Trois garanties :

        * **Périmètre** : les postes sont dérivés de `get_supervision_data`,
          donc exactement ceux affichés à l'écran. Aucun `post_id` n'est
          accepté en paramètre — impossible de faire pinger un poste d'un
          autre client, ou d'énumérer des adresses IP hors périmètre.
        * **Coût** : chaque `ping` bloque son thread jusqu'à
          `PING_TIMEOUT_SECONDS`. Les lectures de base sont faites en amont,
          puis les pings partent en parallèle.
        * **Plafond** : les pings réels sont plafonnés à
          `PING_BATCH_MAX_PINGS` (les postes sans IP n'en coûtent aucun). Le
          nombre de postes écartés est RENVOYÉ à l'appelant — un ping en
          silence manquant serait affiché comme « pas encore mesuré », ce
          qui est trompeur.

        La connexion PostgreSQL n'est JAMAIS touchée depuis ces threads
        (une `Connection` psycopg n'est pas partageable entre threads) :
        `_ping_host` est statique et ne fait qu'appeler le sous-système.
        """
        post_ids = [
            post["post_id"]
            for site in self.get_supervision_data(user)
            for post in site["posts"]
        ]
        if not post_ids:
            return {}, 0

        rows = self.conn.execute(
            "SELECT post_id, ip_address FROM posts WHERE post_id = ANY(%s)",
            (post_ids,),
        ).fetchall()
        ips = {r["post_id"]: (r["ip_address"] or "").strip() for r in rows}

        # Poste sans IP : résultat déterministe, aucun sous-processus à
        # lancer (et aucun temps perdu sur le plafond de pings).
        results: dict[int, dict] = {
            post_id: {
                "reachable": False,
                "rtt_ms": None,
                "message": "Aucune adresse IP enregistrée pour ce poste.",
            }
            for post_id, ip in ips.items() if not ip
        }

        # Postes avec IP : tri par `post_id` pour que le lot soit
        # déterministe (sinon l'ordre de `= ANY(...)` n'est pas garanti et
        # l'écart change d'un refresh à l'autre).
        targets = sorted(pid for pid, ip in ips.items() if ip)
        skipped = max(0, len(targets) - PING_BATCH_MAX_PINGS)
        if skipped:
            logger.warning(
                "Ping automatique plafonné à %s postes : %s poste(s) avec IP "
                "non testés. Augmenter PING_BATCH_MAX_PINGS si nécessaire.",
                PING_BATCH_MAX_PINGS, skipped,
            )
            targets = targets[:PING_BATCH_MAX_PINGS]

        if targets:
            max_workers = max(1, min(PING_BATCH_MAX_WORKERS, len(targets)))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                results.update(
                    dict(
                        pool.map(
                            lambda post_id: (post_id, self._ping_host(ips[post_id])),
                            targets,
                        )
                    )
                )
        return results, skipped

    @staticmethod
    def _ping_host(ip: str | None) -> dict:
        """Ping ICMP d'une adresse, sans aucune dépendance à la base.

        Isolé de `ping_post` pour être réutilisé par le ping en lot, qui
        l'appelle depuis plusieurs threads (cf. `ping_all_posts`).
        """
        ip = (ip or "").strip()
        if not ip:
            return {
                "reachable": False,
                "rtt_ms": None,
                "message": "Aucune adresse IP enregistrée pour ce poste.",
            }

        host = "127.0.0.1" if ip.lower() in {"localhost"} else ip
        if platform.system().lower() == "windows":
            params = ["ping", "-n", "1", "-w", f"{PING_TIMEOUT_SECONDS * 1000}", host]
        else:
            params = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_SECONDS), host]

        try:
            result = subprocess.run(
                params, capture_output=True, text=True, timeout=PING_TIMEOUT_SECONDS + 2,
            )
            output = (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired:
            return {"reachable": False, "rtt_ms": None, "message": "Délai dépassé (timeout)."}
        except Exception as exc:
            logger.warning("Ping impossible vers %s : %s", ip, exc)
            return {"reachable": False, "rtt_ms": None, "message": f"Ping impossible : {exc}"}

        rtt = SupervisionService._extract_rtt_ms(output)
        if rtt is None:
            return {"reachable": False, "rtt_ms": None, "message": "Poste injoignable."}

        return {"reachable": True, "rtt_ms": rtt, "message": f"Réponse en {rtt:.0f} ms."}

    @staticmethod
    def _extract_rtt_ms(output: str) -> float | None:
        """Extrait la latence moyenne (ms) depuis la sortie de la commande ping.

        Gère les syntaxes Windows (temps<1ms, temps=2ms) et Unix/Linux
        (time=1.23 ms, time<1 ms).
        """
        match = re.search(r"temps[=<\/]?\s*([0-9]*\.?[0-9]+)\s*ms", output, re.IGNORECASE)
        if match:
            return float(match.group(1))
        match = re.search(r"time[=<\/]?\s*([0-9]*\.?[0-9]+)\s*ms", output, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None