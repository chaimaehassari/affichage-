import json
import logging
import time
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg import Connection

from app.core.config import get_settings
from app.core.times import get_app_tz, to_utc
from app.sftp.client import SFTPClient

logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_AFFLUENCE_START_HOUR = 8
DEFAULT_AFFLUENCE_END_HOUR = 17
DEFAULT_LARGE_MEDIA_THRESHOLD_MB = 20


class SyncService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def get_job(self, job_id: int) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM sync_jobs WHERE sync_job_id = %s",
            (job_id,),
        ).fetchone()

    def check_running_sync(self, post_id: int) -> dict | None:
        return self.conn.execute(
            """
            SELECT * FROM sync_jobs
            WHERE post_id = %s AND status IN ('PENDING', 'RUNNING')
            """,
            (post_id,),
        ).fetchone()

    def create_job(self, post_id: int, scheduled_at: datetime | None = None, sync_profile_id: int | None = None) -> dict:
        if sync_profile_id is not None:
            try:
                return self.conn.execute(
                    """
                    INSERT INTO sync_jobs (post_id, status, scheduled_at, sync_profile_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (post_id, 'SCHEDULED' if scheduled_at else 'PENDING', scheduled_at, sync_profile_id),
                ).fetchone()
            except psycopg.errors.UndefinedColumn:
                logger.warning(
                    "sync_jobs.sync_profile_id manquante : exécuter la migration "
                    "009_add_sync_profile_to_jobs.sql"
                )
        return self.conn.execute(
            """
            INSERT INTO sync_jobs (post_id, status, scheduled_at)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (post_id, 'SCHEDULED' if scheduled_at else 'PENDING', scheduled_at),
        ).fetchone()

    def get_due_scheduled_jobs(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        return self.conn.execute(
            """
            SELECT * FROM sync_jobs
            WHERE status = 'SCHEDULED' AND scheduled_at IS NOT NULL AND scheduled_at <= %s
            """,
            (now,),
        ).fetchall()

    def schedule_auto_syncs(self) -> int:
        """Crée les jobs programmés du jour pour tous les postes actifs.

        Lit les réglages globaux sync_auto_enabled / sync_auto_schedule /
        sync_auto_time / sync_auto_profile_id (table general_settings).
        Un job au plus par poste et par jour (dans le fuseau de l'application).
        Retourne le nombre de jobs créés.
        """
        from app.services.settings_service import SettingsService

        settings = SettingsService(self.conn).get_all_settings()
        if not settings["sync_auto_enabled"] or settings["sync_auto_schedule"] != "deferred":
            return 0
        try:
            hour, minute = (int(part) for part in settings["sync_auto_time"].split(":"))
        except (AttributeError, ValueError):
            return 0
        try:
            profile_id = int(settings["sync_auto_profile_id"]) if settings["sync_auto_profile_id"] else None
        except (TypeError, ValueError):
            profile_id = None

        tz = get_app_tz()
        now = datetime.now(tz)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < target:
            return 0

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_start_utc = to_utc(day_start)
        day_end_utc = to_utc(day_end)
        scheduled_at = to_utc(target)

        posts = self.conn.execute(
            "SELECT post_id FROM posts WHERE is_active = TRUE ORDER BY post_id"
        ).fetchall()
        created = 0
        for row in posts:
            post_id = row["post_id"]
            exists = self.conn.execute(
                """
                SELECT 1 FROM sync_jobs
                WHERE post_id = %s AND created_at >= %s AND created_at < %s
                LIMIT 1
                """,
                (post_id, day_start_utc, day_end_utc),
            ).fetchone()
            if exists:
                continue
            self.create_job(post_id, scheduled_at, sync_profile_id=profile_id)
            created += 1
        if created:
            self.conn.commit()
        return created

    def mark_job_pending(self, job_id: int) -> None:
        self._update_job(job_id, status="PENDING", scheduled_at=None)

    def generate_config(self, post_id: int) -> dict:
        post = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            raise ValueError("Poste introuvable.")

        config = self.conn.execute(
            "SELECT * FROM post_configurations WHERE post_id = %s",
            (post_id,),
        ).fetchone()

        layout_data = None
        if config and config["layout_id"]:
            layout = self.conn.execute(
                "SELECT * FROM layouts WHERE layout_id = %s",
                (config["layout_id"],),
            ).fetchone()
            if layout:
                zones = self.conn.execute(
                    """
                    SELECT * FROM layout_zones
                    WHERE layout_id = %s
                    ORDER BY zone_number
                    """,
                    (layout["layout_id"],),
                ).fetchall()
                layout_data = {
                    "layout_id": layout["layout_id"],
                    "zones": [
                        {
                            "zone_number": z["zone_number"],
                            "position_x": float(z["position_x"]),
                            "position_y": float(z["position_y"]),
                            "width": float(z["width"]),
                            "height": float(z["height"]),
                            "is_active": z["is_active"],
                        }
                        for z in zones
                    ],
                }

        zone_media_items = self.conn.execute(
            """
            SELECT zm.*, m.name AS media_name, m.media_type, m.sftp_path, m.page_count
            FROM zone_media zm
            LEFT JOIN media m ON m.media_id = zm.media_id
            WHERE zm.post_id = %s
            ORDER BY zm.zone_number, zm.display_order
            """,
            (post_id,),
        ).fetchall()

        zones_data = self._group_zones_playlists(zone_media_items)

        schedules = self.conn.execute(
            "SELECT * FROM schedules WHERE post_id = %s",
            (post_id,),
        ).fetchall()

        loop_enabled = config["loop_enabled"] if config else True

        return {
            "post_id": post["post_id"],
            "code": post["code"],
            "name": post["name"],
            "layout": layout_data,
            "zones": zones_data,
            "loop_enabled": loop_enabled,
            "schedule_enabled": config["schedule_enabled"] if config else False,
            "display_enabled": config["display_enabled"] if config else True,
            "schedules": [
                {
                    "name": s["name"],
                    "start_date": s["start_date"].isoformat() if s["start_date"] else None,
                    "end_date": s["end_date"].isoformat() if s["end_date"] else None,
                    "start_time": s["start_time"].isoformat() if s["start_time"] else None,
                    "end_time": s["end_time"].isoformat() if s["end_time"] else None,
                    "days_of_week": s["days_of_week"],
                    "is_active": s["is_active"],
                }
                for s in schedules
            ],
        }

    def _group_zones_playlists(self, zone_media_items: list[dict]) -> list[dict]:
        """Regroupe les médias par zone en une playlist ordonnée.

        Chaque zone n'apparaît qu'une seule fois dans le résultat. La playlist
        respecte l'ordre d'affichage (display_order) et conserve pour chaque
        média ses paramètres (id, nom, type, fichier, durée).
        Un champ ``media`` conserve le premier élément de la playlist pour
        rester compatible avec les consommateurs existants du format zone.
        """
        zones: dict[int, dict] = {}
        for zm in zone_media_items:
            if not zm["media_id"]:
                continue
            zone = zones.get(zm["zone_number"])
            if zone is None:
                zone = {"zone_number": zm["zone_number"], "media_playlist": []}
                zones[zm["zone_number"]] = zone

            entry = {
                "media_id": zm["media_id"],
                "name": zm["media_name"],
                "media_type": zm["media_type"],
                "filename": zm["sftp_path"],
                "duration_seconds": zm.get("duration_seconds"),
                "display_order": zm.get("display_order"),
            }
            zone["media_playlist"].append(entry)

        # Préserver l'ordre des zones et mettre le premier média en référence.
        ordered = [zones[k] for k in sorted(zones)]
        for zone in ordered:
            zone["media"] = zone["media_playlist"][0] if zone["media_playlist"] else None
        return ordered

    def _update_job(self, job_id: int, **kwargs):
        if not kwargs:
            return
        set_parts = ", ".join(f"{k} = %s" for k in kwargs)
        params = list(kwargs.values()) + [job_id]
        self.conn.execute(f"UPDATE sync_jobs SET {set_parts} WHERE sync_job_id = %s", params)
        self.conn.commit()

    def _update_item(self, item_id: int, **kwargs):
        if not kwargs:
            return
        set_parts = ", ".join(f"{k} = %s" for k in kwargs)
        params = list(kwargs.values()) + [item_id]
        self.conn.execute(f"UPDATE sync_items SET {set_parts} WHERE sync_item_id = %s", params)
        self.conn.commit()

    def _get_affluence_config(self) -> dict:
        row = self.conn.execute(
            """
            SELECT setting_key, setting_value FROM general_settings
            WHERE setting_key IN ('affluence_start_hour', 'affluence_end_hour', 'affluence_media_threshold_mb')
            """
        ).fetchall()
        config = {r["setting_key"]: r["setting_value"] for r in row}
        try:
            start = int(config.get("affluence_start_hour") or DEFAULT_AFFLUENCE_START_HOUR)
            end = int(config.get("affluence_end_hour") or DEFAULT_AFFLUENCE_END_HOUR)
            threshold_mb = int(config.get("affluence_media_threshold_mb") or DEFAULT_LARGE_MEDIA_THRESHOLD_MB)
        except (TypeError, ValueError):
            start, end, threshold_mb = DEFAULT_AFFLUENCE_START_HOUR, DEFAULT_AFFLUENCE_END_HOUR, DEFAULT_LARGE_MEDIA_THRESHOLD_MB
        if end <= start:
            start, end = DEFAULT_AFFLUENCE_START_HOUR, DEFAULT_AFFLUENCE_END_HOUR
        if threshold_mb <= 0:
            threshold_mb = DEFAULT_LARGE_MEDIA_THRESHOLD_MB
        return {"start_hour": start, "end_hour": end, "threshold_mb": threshold_mb}

    def run_sync(self, post_id: int, job_id: int, media_ids: list[int] | None = None):
        job = self.get_job(job_id)
        if not job:
            logger.info(f"Job {job_id} not found")
            return

        logger.info(f"Starting sync for job {job_id}, post {post_id}")
        self._update_job(job_id, status="RUNNING", started_at=datetime.now(timezone.utc))

        try:
            config_data = self.generate_config(post_id)
            post_code = config_data["code"]
            root = settings.SFTP_ROOT_PATH.rstrip("/")
            player_dir = f"{root}/players/{post_code}"
            media_dir = f"{player_dir}/media"

            logger.info(f"Config generated for post {post_code}, zones: {len(config_data.get('zones', []))}")

            config_json = json.dumps(config_data, indent=2, ensure_ascii=False)
            config_bytes = config_json.encode("utf-8")
            total_bytes = len(config_bytes)

            config_item = self.conn.execute(
                """
                INSERT INTO sync_items (sync_job_id, item_type, item_path, status)
                VALUES (%s, 'CONFIG', %s, 'PENDING')
                RETURNING sync_item_id
                """,
                (job_id, f"{player_dir}/config.json"),
            ).fetchone()
            config_item_id = config_item["sync_item_id"]
            self.conn.commit()

            logger.info(f"Connecting to SFTP at {settings.SFTP_HOST}:{settings.SFTP_PORT}")
            with SFTPClient() as sftp:
                logger.info("SFTP connected")

                all_files = []
                for zone in config_data.get("zones", []):
                    playlist = zone.get("media_playlist") or []
                    for media_info in playlist:
                        if media_info and media_info.get("filename"):
                            if media_ids is not None and media_info["media_id"] not in media_ids:
                                continue
                            remote_src = f"{root}/{media_info['filename']}"
                            size = sftp.remote_file_size(remote_src)
                            if size is not None:
                                all_files.append({
                                    "media_id": media_info["media_id"],
                                    "remote_src": remote_src,
                                    "remote_name": media_info["filename"],
                                    "remote_path": f"{media_dir}/{media_info['filename']}",
                                    "size": size,
                                })

                now_hour = datetime.now().hour
                affluence = self._get_affluence_config()
                in_affluence = affluence["start_hour"] <= now_hour < affluence["end_hour"]
                threshold_bytes = affluence["threshold_mb"] * 1024 * 1024
                media_files = [
                    f for f in all_files
                    if not (in_affluence and f["size"] > threshold_bytes)
                ]
                deferred_files = [
                    f for f in all_files
                    if in_affluence and f["size"] > threshold_bytes
                ]

                for f in media_files:
                    total_bytes += f["size"]

                for f in deferred_files:
                    self.conn.execute(
                        """
                        INSERT INTO sync_items (sync_job_id, media_id, item_type, item_path, status)
                        VALUES (%s, %s, 'MEDIA', %s, 'DEFERRED')
                        """,
                        (job_id, f["media_id"], f["remote_path"]),
                    )
                    self.conn.commit()
                    logger.info(
                        f"Report du gros média {f['media_id']} ({f['size']} o) "
                        f"durant la période d'affluence ({now_hour}h)."
                    )

                total_files = 1 + len(media_files)

                media_items = []
                for mf in media_files:
                    item = self.conn.execute(
                        """
                        INSERT INTO sync_items (sync_job_id, media_id, item_type, item_path, status)
                        VALUES (%s, %s, 'MEDIA', %s, 'PENDING')
                        RETURNING sync_item_id
                        """,
                        (job_id, mf["media_id"], mf["remote_path"]),
                    ).fetchone()
                    self.conn.commit()
                    media_items.append((item["sync_item_id"], mf))

                self._update_item(config_item_id, status="UPLOADING", progress_percent=0)
                start_time = time.time()
                sftp.upload_bytes(config_bytes, f"{player_dir}/config.json")
                elapsed = max(time.time() - start_time, 0.01)
                speed = int(len(config_bytes) / elapsed / 1024)
                self._update_item(config_item_id, status="COMPLETED", progress_percent=100)
                self._update_job(job_id, progress_percent=int(100 / total_files), transfer_speed=speed)

                uploaded_bytes = len(config_bytes)

                for item_id, mf in media_items:
                    self._update_item(item_id, status="UPLOADING", progress_percent=0)
                    try:
                        start_time = time.time()
                        remote_exists = sftp.exists(mf["remote_path"])
                        if remote_exists and sftp.remote_file_size(mf["remote_path"]) == mf["size"]:
                            self._update_item(item_id, status="COMPLETED", progress_percent=100)
                            uploaded_bytes += mf["size"]
                            progress = int((uploaded_bytes / total_bytes) * 100) if total_bytes > 0 else 100
                            self._update_job(job_id, progress_percent=min(progress, 99))
                            continue

                        sftp.copy_file(mf["remote_src"], mf["remote_path"])
                        elapsed = max(time.time() - start_time, 0.01)
                        speed = int(mf["size"] / elapsed / 1024)
                        uploaded_bytes += mf["size"]
                        progress = int((uploaded_bytes / total_bytes) * 100) if total_bytes > 0 else 100
                        self._update_item(item_id, status="COMPLETED", progress_percent=100)
                        self._update_job(job_id, progress_percent=min(progress, 99), transfer_speed=speed)
                    except Exception as e:
                        self._update_item(item_id, status="FAILED", progress_percent=0)
                        self._update_job(job_id, transfer_speed=0)

            logger.info(f"Sync completed for job {job_id}")
            self._update_job(
                job_id,
                status="COMPLETED",
                progress_percent=100,
                completed_at=datetime.now(timezone.utc),
                transfer_speed=0,
            )
            self.conn.execute(
                """
                UPDATE posts
                SET last_sync_at = %s, is_up_to_date = TRUE
                WHERE post_id = %s
                """,
                (datetime.now(timezone.utc), post_id),
            )
            synced_media_ids = set()
            for mf in media_files:
                synced_media_ids.add(mf["media_id"])
            for item_id_item, mf in media_items:
                synced_media_ids.add(mf["media_id"])
            self._upsert_media_sync_state(post_id, synced_media_ids, "SYNCED")
            all_config_media = set()
            for zone in config_data.get("zones", []):
                for mi in (zone.get("media_playlist") or []):
                    if mi and mi.get("media_id"):
                        if media_ids is None or mi["media_id"] in media_ids:
                            all_config_media.add(mi["media_id"])
            skipped_media = all_config_media - synced_media_ids
            if skipped_media:
                self._upsert_media_sync_state(post_id, skipped_media, "SYNCED")
            self.conn.commit()
        except Exception as e:
            logger.info(f"Sync FAILED for job {job_id}: {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            self._update_job(
                job_id,
                status="FAILED",
                error_message=str(e)[:1000],
                completed_at=datetime.now(timezone.utc),
            )

    def _upsert_media_sync_state(self, post_id: int, media_ids: set, status: str):
        now = datetime.now(timezone.utc)
        for mid in media_ids:
            try:
                self.conn.execute(
                    """
                    INSERT INTO media_sync_state (media_id, post_id, synced_at, status)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (media_id, post_id) DO UPDATE
                    SET synced_at = EXCLUDED.synced_at, status = EXCLUDED.status
                    """,
                    (mid, post_id, now, status),
                )
            except Exception:
                logger.debug("media_sync_state table missing, skipping sync state update")
                break

    def get_group_media_hierarchy(self, group_id: int) -> list[dict]:
        posts = self.conn.execute(
            "SELECT post_id FROM screen_group_posts WHERE group_id = %s ORDER BY post_id",
            (group_id,),
        ).fetchall()
        if not posts:
            return []
        rep_post_id = posts[0]["post_id"]
        zone_media_items = self.conn.execute(
            """
            SELECT zm.*, m.name AS media_name, m.media_type, m.sftp_path
            FROM zone_media zm
            LEFT JOIN media m ON m.media_id = zm.media_id
            WHERE zm.post_id = %s
            ORDER BY zm.zone_number, zm.display_order
            """,
            (rep_post_id,),
        ).fetchall()
        media_ids = set()
        for zm in zone_media_items:
            if zm["media_id"]:
                media_ids.add(zm["media_id"])
        sync_states = {}
        if media_ids:
            try:
                rows = self.conn.execute(
                    """
                    SELECT mss.media_id, mss.status, mss.synced_at
                    FROM media_sync_state mss
                    WHERE mss.media_id = ANY(%s) AND mss.post_id = ANY(%s)
                    """,
                    (list(media_ids), [p["post_id"] for p in posts]),
                ).fetchall()
                all_post_ids = [p["post_id"] for p in posts]
                post_count = len(all_post_ids)
                media_post_sync = {}
                for r in rows:
                    mid = r["media_id"]
                    if mid not in media_post_sync:
                        media_post_sync[mid] = {"synced": 0, "total": post_count, "latest_status": r["status"]}
                    if r["status"] == "SYNCED":
                        media_post_sync[mid]["synced"] += 1
                for mid in media_ids:
                    if mid in media_post_sync:
                        info = media_post_sync[mid]
                        if info["synced"] == info["total"]:
                            sync_states[mid] = {"status": "SYNCED", "synced_at": None}
                        elif info["synced"] > 0:
                            latest = self.conn.execute(
                                "SELECT synced_at FROM media_sync_state WHERE media_id = %s AND post_id = ANY(%s) AND status = 'SYNCED' ORDER BY synced_at DESC LIMIT 1",
                                (mid, all_post_ids),
                            ).fetchone()
                            sync_states[mid] = {"status": "PARTIAL", "synced_at": latest["synced_at"].isoformat() if latest and latest["synced_at"] else None}
                        else:
                            sync_states[mid] = {"status": info["latest_status"], "synced_at": None}
                    else:
                        sync_states[mid] = {"status": "NOT_SYNCED", "synced_at": None}
            except Exception:
                logger.debug("media_sync_state table missing, returning all media as NOT_SYNCED")
                for mid in media_ids:
                    sync_states[mid] = {"status": "NOT_SYNCED", "synced_at": None}
        zones: dict[int, dict] = {}
        for zm in zone_media_items:
            if not zm["media_id"]:
                continue
            zn = zm["zone_number"]
            if zn not in zones:
                zones[zn] = {"zone_number": zn, "media": []}
            st = sync_states.get(zm["media_id"], {"status": "NOT_SYNCED", "synced_at": None})
            zones[zn]["media"].append({
                "media_id": zm["media_id"],
                "name": zm["media_name"],
                "media_type": zm["media_type"],
                "filename": zm["sftp_path"],
                "duration_seconds": zm.get("duration_seconds"),
                "display_order": zm.get("display_order"),
                "sync_status": st["status"],
                "synced_at": st["synced_at"],
            })
        return [zones[k] for k in sorted(zones)]

    def get_media_sync_states_for_group(self, group_id: int) -> dict:
        posts = self.conn.execute(
            "SELECT post_id FROM screen_group_posts WHERE group_id = %s",
            (group_id,),
        ).fetchall()
        if not posts:
            return {}
        post_ids = [p["post_id"] for p in posts]
        zone_media_rows = self.conn.execute(
            """
            SELECT DISTINCT zm.media_id
            FROM zone_media zm
            WHERE zm.post_id = ANY(%s) AND zm.media_id IS NOT NULL
            """,
            (post_ids,),
        ).fetchall()
        if not zone_media_rows:
            return {}
        media_ids = [r["media_id"] for r in zone_media_rows]
        try:
            rows = self.conn.execute(
                """
                SELECT mss.media_id, mss.post_id, mss.status, mss.synced_at
                FROM media_sync_state mss
                WHERE mss.media_id = ANY(%s) AND mss.post_id = ANY(%s)
                """,
                (media_ids, post_ids),
            ).fetchall()
        except Exception:
            logger.debug("media_sync_state table missing, returning all media as NOT_SYNCED")
            rows = []
        result = {}
        post_count = len(post_ids)
        for mid in media_ids:
            post_states = [r for r in rows if r["media_id"] == mid]
            synced_count = sum(1 for r in post_states if r["status"] == "SYNCED")
            if synced_count == post_count:
                latest = max((r["synced_at"] for r in post_states if r["synced_at"] and r["status"] == "SYNCED"), default=None)
                result[mid] = {"status": "SYNCED", "synced_at": latest.isoformat() if latest else None, "synced_posts": synced_count, "total_posts": post_count}
            elif synced_count > 0:
                latest = max((r["synced_at"] for r in post_states if r["synced_at"] and r["status"] == "SYNCED"), default=None)
                result[mid] = {"status": "PARTIAL", "synced_at": latest.isoformat() if latest else None, "synced_posts": synced_count, "total_posts": post_count}
            elif any(r["status"] == "SYNCING" for r in post_states):
                result[mid] = {"status": "SYNCING", "synced_at": None, "synced_posts": 0, "total_posts": post_count}
            elif any(r["status"] == "FAILED" for r in post_states):
                result[mid] = {"status": "FAILED", "synced_at": None, "synced_posts": 0, "total_posts": post_count}
            else:
                result[mid] = {"status": "NOT_SYNCED", "synced_at": None, "synced_posts": 0, "total_posts": post_count}
        return result