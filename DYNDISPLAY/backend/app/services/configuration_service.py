from datetime import datetime, timezone

from psycopg import Connection

from app.schemas.configuration import (
    PostConfigurationUpdate,
    ScheduleCreate,
    ScheduleUpdate,
    ZoneMediaAssignment,
)
from app.services.zone_access import assert_zone_allowed


def _schedule_dict(s: dict) -> dict:
    return {
        "schedule_id": s["schedule_id"],
        "post_id": s["post_id"],
        "name": s["name"],
        "start_date": s["start_date"].isoformat() if s["start_date"] else None,
        "end_date": s["end_date"].isoformat() if s["end_date"] else None,
        "start_time": s["start_time"].isoformat() if s["start_time"] else None,
        "end_time": s["end_time"].isoformat() if s["end_time"] else None,
        "days_of_week": s["days_of_week"],
        "is_active": s["is_active"],
        "created_at": s["created_at"].isoformat() if s["created_at"] else None,
        "updated_at": s["updated_at"].isoformat() if s["updated_at"] else None,
    }


class ConfigurationService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def get_or_create_config(self, post_id: int) -> dict:
        row = self.conn.execute(
            """
            INSERT INTO post_configurations (post_id, layout_id, loop_enabled, schedule_enabled,
                                             display_enabled, version_number)
            VALUES (%s, NULL, TRUE, FALSE, TRUE, 1)
            ON CONFLICT (post_id) DO NOTHING
            RETURNING *
            """,
            (post_id,),
        ).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT * FROM post_configurations WHERE post_id = %s",
                (post_id,),
            ).fetchone()
        return row

    def get_configuration(self, post_id: int) -> dict | None:
        post = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            return None

        config = self.get_or_create_config(post_id)
        layout = None
        active_zones = []

        if config["layout_id"]:
            db_layout = self.conn.execute(
                "SELECT * FROM layouts WHERE layout_id = %s",
                (config["layout_id"],),
            ).fetchone()
            if db_layout:
                zones = self.conn.execute(
                    """
                    SELECT * FROM layout_zones
                    WHERE layout_id = %s
                    ORDER BY zone_number
                    """,
                    (db_layout["layout_id"],),
                ).fetchall()
                layout = {
                    "layout_id": db_layout["layout_id"],
                    "is_active": db_layout["is_active"],
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
                active_zones = [z for z in zones if z["is_active"]]

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
        media_by_zone = {zm["zone_number"]: [] for zm in zone_media_items}

        for zm in zone_media_items:
            if zm["zone_number"] not in media_by_zone:
                media_by_zone[zm["zone_number"]] = []
            media_by_zone[zm["zone_number"]].append(zm)

        zones = []
        for z in active_zones:
            zm_list = media_by_zone.get(z["zone_number"], [])
            playlists = []
            for zm in zm_list:
                if not zm["media_id"]:
                    continue
                media_obj = zm
                media_data = {
                    "media_id": media_obj["media_id"],
                    "name": media_obj["media_name"],
                    "media_type": media_obj["media_type"],
                    "url": f"/media/{media_obj['sftp_path']}" if media_obj["sftp_path"] else None,
                    "duration_seconds": zm.get("duration_seconds"),
                }
                if media_obj["media_type"] == "PDF":
                    page_count = media_obj.get("page_count")
                    if page_count:
                        import os, re
                        base = os.path.splitext(os.path.basename(media_obj["sftp_path"]))[0]
                        ts_match = re.match(r"^(\d+)_", base)
                        ts = ts_match.group(1) if ts_match else base
                        media_data["pdf_pages"] = [
                            f"/media/pdfs/{ts}_page_{i}.png"
                            for i in range(1, page_count + 1)
                        ]
                playlists.append(media_data)
            zones.append({
                "zone_number": z["zone_number"],
                "position_x": float(z["position_x"]),
                "position_y": float(z["position_y"]),
                "width": float(z["width"]),
                "height": float(z["height"]),
                "is_active": z["is_active"],
                "media": playlists[0] if playlists else None,
                "media_playlist": playlists,
            })

        schedules = self.conn.execute(
            """
            SELECT * FROM schedules
            WHERE post_id = %s
            ORDER BY created_at
            """,
            (post_id,),
        ).fetchall()

        return {
            "post_id": post["post_id"],
            "code": post["code"],
            "name": post["name"],
            "layout": layout,
            "zones": zones,
            "loop_enabled": config["loop_enabled"],
            "schedule_enabled": config["schedule_enabled"],
            "display_enabled": config["display_enabled"],
            "schedules": [_schedule_dict(s) for s in schedules],
        }

    def update_configuration(self, post_id: int, data: PostConfigurationUpdate, user_id: int) -> dict:
        post = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            raise ValueError("Poste introuvable.")

        config = self.get_or_create_config(post_id)

        layout_id = config["layout_id"]
        if data.layout_id is not None:
            layout = self.conn.execute(
                "SELECT layout_id FROM layouts WHERE layout_id = %s",
                (data.layout_id,),
            ).fetchone()
            if not layout:
                raise ValueError("Modèle introuvable.")
            layout_id = data.layout_id

        self.conn.execute(
            """
            UPDATE post_configurations
            SET layout_id = %s, loop_enabled = %s, schedule_enabled = %s, display_enabled = %s,
                version_number = COALESCE(version_number, 0) + 1, updated_at = %s
            WHERE post_id = %s
            """,
            (layout_id, data.loop_enabled, data.schedule_enabled, data.display_enabled,
             datetime.now(timezone.utc), post_id),
        )

        for assignment in data.zones:
            assert_zone_allowed(self.conn, user_id, assignment.zone_number)

        self._rebuild_zones_playlists(post_id, data.zones)

        return self.get_configuration(post_id)

    def update_zones(self, post_id: int, zones: list[ZoneMediaAssignment], user_id: int) -> None:
        post = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            raise ValueError("Poste introuvable.")

        for assignment in zones:
            assert_zone_allowed(self.conn, user_id, assignment.zone_number)

        self._rebuild_zones_playlists(post_id, zones)

    def _rebuild_zones_playlists(self, post_id: int, assignments: list) -> None:
        grouped = {}
        for a in assignments:
            grouped.setdefault(a.zone_number, []).append(a)

        for zone_number, items in grouped.items():
            self.conn.execute(
                "DELETE FROM zone_media WHERE post_id = %s AND zone_number = %s",
                (post_id, zone_number),
            )
            has_media = False
            for item in items:
                if item.media_id is not None:
                    has_media = True
            if not has_media:
                continue
            for idx, item in enumerate(items, start=1):
                if item.media_id is None:
                    continue
                media = self.conn.execute(
                    "SELECT media_id, media_type FROM media WHERE media_id = %s",
                    (item.media_id,),
                ).fetchone()
                if not media:
                    raise ValueError(f"Média introuvable : {item.media_id}")
                duration = getattr(item, "duration_seconds", None)
                if duration is not None and media["media_type"] in ("IMAGE", "PDF") and duration < 3:
                    raise ValueError("La durée d'affichage doit être d'au moins 3 secondes.")
                if media["media_type"] in ("IMAGE", "PDF") and duration is not None and duration > 60:
                    raise ValueError("La durée d'affichage ne doit pas dépasser 60 secondes.")
                order = getattr(item, "display_order", None) or idx
                self.conn.execute(
                    """
                    INSERT INTO zone_media (post_id, zone_number, media_id, display_order, duration_seconds, is_active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    """,
                    (post_id, zone_number, item.media_id, order, duration),
                )

    def _apply_zone_assignment(self, post_id: int, assignment: ZoneMediaAssignment) -> None:
        if isinstance(assignment, ZoneMediaAssignment):
            media_id = assignment.media_id
            duration = assignment.duration_seconds
            order = assignment.display_order
        else:
            media_id = getattr(assignment, "media_id", None)
            duration = getattr(assignment, "duration_seconds", None)
            order = getattr(assignment, "display_order", None)

        if media_id is None:
            self.conn.execute(
                "DELETE FROM zone_media WHERE post_id = %s AND zone_number = %s",
                (post_id, assignment.zone_number),
            )
            return

        media = self.conn.execute(
            "SELECT media_id, media_type FROM media WHERE media_id = %s",
            (media_id,),
        ).fetchone()
        if not media:
            raise ValueError(f"Média introuvable : {media_id}")

        if duration is not None and media["media_type"] in ("IMAGE", "PDF") and duration < 3:
            raise ValueError("La durée d'affichage doit être d'au moins 3 secondes.")

        if media["media_type"] in ("IMAGE", "PDF") and duration is not None and duration > 60:
            raise ValueError("La durée d'affichage ne doit pas dépasser 60 secondes.")

        if order is not None and order < 1:
            raise ValueError("L'ordre d'affichage doit être positif.")

        next_order = order if order is not None else self._next_display_order(post_id, assignment.zone_number)

        existing = self.conn.execute(
            """
            SELECT zone_media_id FROM zone_media
            WHERE post_id = %s AND zone_number = %s AND media_id = %s
            """,
            (post_id, assignment.zone_number, media_id),
        ).fetchone()

        if existing:
            updates = ["updated_at = %s"]
            params = [datetime.now(timezone.utc)]
            if duration is not None:
                updates.append("duration_seconds = %s")
                params.append(duration)
            if order is not None:
                updates.append("display_order = %s")
                params.append(order)
            params.append(existing["zone_media_id"])
            self.conn.execute(
                f"UPDATE zone_media SET {', '.join(updates)} WHERE zone_media_id = %s",
                params,
            )
        else:
            self.conn.execute(
                """
                INSERT INTO zone_media (post_id, zone_number, media_id, display_order, duration_seconds, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                """,
                (post_id, assignment.zone_number, media_id, next_order, duration),
            )

    def _next_display_order(self, post_id: int, zone_number: int) -> int:
        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(display_order), 0) AS max_order
            FROM zone_media
            WHERE post_id = %s AND zone_number = %s
            """,
            (post_id, zone_number),
        ).fetchone()
        return int(row["max_order"]) + 1


class ScheduleService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def list_schedules(self, post_id: int) -> list[dict]:
        schedules = self.conn.execute(
            """
            SELECT * FROM schedules
            WHERE post_id = %s
            ORDER BY created_at
            """,
            (post_id,),
        ).fetchall()
        return [_schedule_dict(s) for s in schedules]

    def create_schedule(self, post_id: int, data: ScheduleCreate) -> dict:
        post = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
        if not post:
            raise ValueError("Poste introuvable.")

        row = self.conn.execute(
            """
            INSERT INTO schedules (post_id, name, start_date, end_date, start_time, end_time,
                                   days_of_week, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (post_id, data.name, data.start_date, data.end_date, data.start_time, data.end_time,
             data.days_of_week, data.is_active),
        ).fetchone()
        return _schedule_dict(row)

    def update_schedule(self, schedule_id: int, data: ScheduleUpdate) -> dict:
        schedule = self.conn.execute(
            "SELECT * FROM schedules WHERE schedule_id = %s",
            (schedule_id,),
        ).fetchone()
        if not schedule:
            raise ValueError("Planning introuvable.")

        fields = []
        params = []
        if data.name is not None:
            fields.append("name = %s")
            params.append(data.name)
        if data.start_date is not None:
            fields.append("start_date = %s")
            params.append(data.start_date)
        if data.end_date is not None:
            fields.append("end_date = %s")
            params.append(data.end_date)
        if data.start_time is not None:
            fields.append("start_time = %s")
            params.append(data.start_time)
        if data.end_time is not None:
            fields.append("end_time = %s")
            params.append(data.end_time)
        if data.days_of_week is not None:
            fields.append("days_of_week = %s")
            params.append(data.days_of_week)
        if data.is_active is not None:
            fields.append("is_active = %s")
            params.append(data.is_active)
        fields.append("updated_at = %s")
        params.append(datetime.now(timezone.utc))
        params.append(schedule_id)

        self.conn.execute(
            f"UPDATE schedules SET {', '.join(fields)} WHERE schedule_id = %s",
            params,
        )
        row = self.conn.execute(
            "SELECT * FROM schedules WHERE schedule_id = %s",
            (schedule_id,),
        ).fetchone()
        return _schedule_dict(row)

    def delete_schedule(self, schedule_id: int) -> None:
        schedule = self.conn.execute(
            "SELECT * FROM schedules WHERE schedule_id = %s",
            (schedule_id,),
        ).fetchone()
        if not schedule:
            raise ValueError("Planning introuvable.")
        self.conn.execute("DELETE FROM schedules WHERE schedule_id = %s", (schedule_id,))