import platform
import re
import subprocess
from datetime import datetime, timezone, timedelta

from psycopg import Connection

HEARTBEAT_OFFLINE_THRESHOLD_SECONDS = 90
PING_TIMEOUT_SECONDS = 5


class SupervisionService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def get_supervision_data(self) -> list[dict]:
        sites = self.conn.execute(
            "SELECT * FROM sites WHERE is_active = TRUE ORDER BY name"
        ).fetchall()
        result = []
        for site in sites:
            posts_data = []
            posts = self.conn.execute(
                "SELECT * FROM posts WHERE site_id = %s AND is_active = TRUE",
                (site["site_id"],),
            ).fetchall()
            for post in posts:
                config = self.conn.execute(
                    "SELECT * FROM post_configurations WHERE post_id = %s",
                    (post["post_id"],),
                ).fetchone()
                display_enabled = config["display_enabled"] if config else True

                status = self._compute_status(post)
                posts_data.append({
                    "post_id": post["post_id"],
                    "code": post["code"],
                    "name": post["name"],
                    "is_online": post["is_online"],
                    "is_up_to_date": post["is_up_to_date"],
                    "last_sync_at": post["last_sync_at"].isoformat() if post["last_sync_at"] else None,
                    "last_heartbeat_at": post["last_heartbeat_at"].isoformat() if post["last_heartbeat_at"] else None,
                    "display_enabled": display_enabled,
                    "status": status,
                })
            result.append({
                "site_id": site["site_id"],
                "code": site["code"],
                "name": site["name"],
                "posts": posts_data,
            })
        return result

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