import logging
import platform
import re
import subprocess
from datetime import datetime, timezone, timedelta

from psycopg import Connection

from app.services.scope import is_admin, is_superadmin, is_regular_admin, admin_client_codes

logger = logging.getLogger(__name__)

HEARTBEAT_OFFLINE_THRESHOLD_SECONDS = 90
PING_TIMEOUT_SECONDS = 5


class SupervisionService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def get_supervision_data(self, user) -> list[dict]:
        if is_superadmin(user):
            return self._all_data()
        if is_regular_admin(user):
            return self._scoped_data(user, admin_client_codes(self.conn, user))
        if is_admin(user):
            return self._all_data()
        return self._scoped_data(user)

    def _all_data(self) -> list[dict]:
        sites = self.conn.execute(
            "SELECT * FROM sites WHERE is_active = TRUE ORDER BY name"
        ).fetchall()
        result = []
        for site in sites:
            posts = self.conn.execute(
                "SELECT * FROM posts WHERE site_id = %s AND is_active = TRUE",
                (site["site_id"],),
            ).fetchall()
            result.append(self._site_out(site, posts))
        return result

    def _scoped_data(self, user, codes: list[str] | None = None) -> list[dict]:
        if codes is None:
            codes = [(user.user_code or "").strip()]
        effective = [c for c in codes if c]
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
            posts_list.append(self._post_out(r))
        for site_id in order:
            result.append(site_by_id[site_id])
        return result

    def _site_out(self, site, posts: list[dict]) -> dict:
        return {
            "site_id": site["site_id"],
            "code": site["code"],
            "name": site["name"],
            "posts": [self._post_out(p) for p in posts],
        }

    def _post_out(self, post: dict) -> dict:
        config = self.conn.execute(
            "SELECT * FROM post_configurations WHERE post_id = %s",
            (post["post_id"],),
        ).fetchone()
        display_enabled = config["display_enabled"] if config else True
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

    def send_heartbeat(self, post_id: int) -> bool:
        post = self.conn.execute(
            "SELECT post_id FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            return False
        self.conn.execute(
            """
            UPDATE posts
            SET is_online = TRUE, last_heartbeat_at = %s
            WHERE post_id = %s
            """,
            (datetime.now(timezone.utc), post_id),
        )
        return True

    def ping_post(self, post_id: int) -> dict:
        """Ping ICMP réel vers l'adresse IP du poste (commande ping du système).

        Retourne la joignabilité et la latence (RTT en millisecondes) mesurée.
        """
        post = self.conn.execute(
            "SELECT post_id, name, ip_address FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            return {"reachable": False, "rtt_ms": None, "message": "Poste introuvable."}

        ip = (post["ip_address"] or "").strip()
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
            logger.warning("Ping impossible pour le poste %s (%s) : %s", post["post_id"], ip, exc)
            return {"reachable": False, "rtt_ms": None, "message": f"Ping impossible : {exc}"}

        rtt = self._extract_rtt_ms(output)
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