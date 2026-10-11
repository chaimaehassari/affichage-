from datetime import datetime, timezone

from psycopg import Connection

from app.schemas.layout import LayoutCreate, LayoutUpdate


class LayoutService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def list_layouts(self) -> list[dict]:
        return self.conn.execute(
            """
            SELECT l.layout_id, l.name, l.is_active, l.created_at, l.updated_at,
                   COUNT(lz.layout_zone_id) FILTER (WHERE lz.is_active) AS active_zone_count
            FROM layouts l
            LEFT JOIN layout_zones lz ON lz.layout_id = l.layout_id
            GROUP BY l.layout_id
            ORDER BY l.name
            """
        ).fetchall()

    def get_layout(self, layout_id: int) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM layouts WHERE layout_id = %s",
            (layout_id,),
        ).fetchone()

    def list_layouts_with_zones(self) -> list[dict]:
        """Liste tous les layouts AVEC leurs zones, en 2 requêtes au total.

        Remplace N appels à get_layout_detail (donc 2N requêtes) par une
        seule lecture groupée. L'écran de configuration affiche les zones de
        tous les modèles en vignettes, d'où l'intérêt d'un lot unique.
        """
        layouts = self.list_layouts()
        if not layouts:
            return []

        rows = self.conn.execute(
            """
            SELECT layout_id, layout_zone_id, zone_number, position_x, position_y,
                   width, height, is_active
            FROM layout_zones
            ORDER BY layout_id, zone_number
            """
        ).fetchall()

        zones_by_layout: dict[int, list[dict]] = {}
        for z in rows:
            zones_by_layout.setdefault(z["layout_id"], []).append(
                {
                    "layout_zone_id": z["layout_zone_id"],
                    "zone_number": z["zone_number"],
                    "position_x": float(z["position_x"]),
                    "position_y": float(z["position_y"]),
                    "width": float(z["width"]),
                    "height": float(z["height"]),
                    "is_active": z["is_active"],
                }
            )

        return [
            {
                "layout_id": layout["layout_id"],
                "name": layout["name"],
                "is_active": layout["is_active"],
                "active_zone_count": layout["active_zone_count"] or 0,
                "zones": zones_by_layout.get(layout["layout_id"], []),
                "created_at": layout["created_at"].isoformat() if layout["created_at"] else None,
                "updated_at": layout["updated_at"].isoformat() if layout["updated_at"] else None,
            }
            for layout in layouts
        ]

    def get_layout_detail(self, layout_id: int) -> dict | None:
        layout = self.get_layout(layout_id)
        if not layout:
            return None

        zones = self.conn.execute(
            """
            SELECT layout_zone_id, zone_number, position_x, position_y, width, height, is_active
            FROM layout_zones
            WHERE layout_id = %s
            ORDER BY zone_number
            """,
            (layout_id,),
        ).fetchall()

        return {
            "layout_id": layout["layout_id"],
            "name": layout["name"],
            "is_active": layout["is_active"],
            "active_zone_count": sum(1 for z in zones if z["is_active"]),
            "zones": [
                {
                    "layout_zone_id": z["layout_zone_id"],
                    "zone_number": z["zone_number"],
                    "position_x": float(z["position_x"]),
                    "position_y": float(z["position_y"]),
                    "width": float(z["width"]),
                    "height": float(z["height"]),
                    "is_active": z["is_active"],
                }
                for z in zones
            ],
            "created_at": layout["created_at"].isoformat() if layout["created_at"] else None,
            "updated_at": layout["updated_at"].isoformat() if layout["updated_at"] else None,
        }

    def create_layout(self, data: LayoutCreate) -> dict:
        existing = self.conn.execute(
            "SELECT layout_id FROM layouts WHERE name = %s",
            (data.name,),
        ).fetchone()
        if existing:
            raise ValueError("Ce nom de modèle existe déjà.")

        row = self.conn.execute(
            "INSERT INTO layouts (name, is_active) VALUES (%s, %s) RETURNING layout_id",
            (data.name, data.is_active),
        ).fetchone()
        layout_id = row["layout_id"]

        for z in data.zones:
            self.conn.execute(
                """
                INSERT INTO layout_zones (layout_id, zone_number, position_x, position_y, width, height, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (layout_id, z.zone_number, z.position_x, z.position_y, z.width, z.height, z.is_active),
            )

        return self.get_layout(layout_id)

    def update_layout(self, layout_id: int, data: LayoutUpdate) -> dict:
        layout = self.get_layout(layout_id)
        if not layout:
            raise ValueError("Modèle introuvable.")

        sql = "UPDATE layouts SET updated_at = %s"
        params = [datetime.now(timezone.utc)]
        if data.name is not None and data.name != layout["name"]:
            existing = self.conn.execute(
                "SELECT layout_id FROM layouts WHERE name = %s AND layout_id != %s",
                (data.name, layout_id),
            ).fetchone()
            if existing:
                raise ValueError("Ce nom de modèle existe déjà.")
            sql += ", name = %s"
            params.append(data.name)
        if data.is_active is not None:
            sql += ", is_active = %s"
            params.append(data.is_active)
        sql += " WHERE layout_id = %s"
        params.append(layout_id)
        self.conn.execute(sql, params)

        if data.zones is not None:
            self.conn.execute("DELETE FROM layout_zones WHERE layout_id = %s", (layout_id,))
            for z in data.zones:
                self.conn.execute(
                    """
                    INSERT INTO layout_zones (layout_id, zone_number, position_x, position_y, width, height, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (layout_id, z.zone_number, z.position_x, z.position_y, z.width, z.height, z.is_active),
                )

        return self.get_layout(layout_id)

    def delete_layout(self, layout_id: int) -> None:
        layout = self.get_layout(layout_id)
        if not layout:
            raise ValueError("Modèle introuvable.")

        self.conn.execute("DELETE FROM layout_zones WHERE layout_id = %s", (layout_id,))
        self.conn.execute("DELETE FROM layouts WHERE layout_id = %s", (layout_id,))