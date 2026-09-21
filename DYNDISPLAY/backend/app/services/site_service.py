import logging
from datetime import datetime, timezone

from psycopg import Connection

from app.schemas.site import (
    BatchAssignMediaRequest,
    GroupCreate,
    GroupUpdate,
    PostCreate,
    PostUpdate,
    SiteCreate,
    SiteUpdate,
)
from app.core.config import get_settings
from app.services.audit_service import log_action
from app.services.zone_access import assert_zone_allowed
from app.services.scope import site_in_scope, scope_sql
from app.sftp.client import SFTPClient

logger = logging.getLogger(__name__)
settings = get_settings()


class SiteService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def list_sites(self, search: str | None = None, scope=None) -> list[dict]:
        sql = """
            SELECT s.site_id, s.code, s.name, s.address, s.description, s.is_active,
                   s.client_code, s.created_at, s.updated_at, COUNT(p.post_id) AS post_count
            FROM sites s
            LEFT JOIN posts p ON p.site_id = s.site_id
        """
        params = []
        clauses = []
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "s.client_code")
            if frag:
                clauses.append(frag.lstrip(" AND "))
            params.extend(args)
        if search:
            term = f"%{search}%"
            clauses.append("(s.code ILIKE %s OR s.name ILIKE %s)")
            params.extend([term, term])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY s.site_id ORDER BY s.code"
        return self.conn.execute(sql, params).fetchall()

    def get_site(self, site_id: int, scope=None) -> dict | None:
        sql = """
            SELECT s.*, COUNT(p.post_id) AS post_count
            FROM sites s
            LEFT JOIN posts p ON p.site_id = s.site_id
            WHERE s.site_id = %s
        """
        params = [site_id]
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "s.client_code")
            if frag:
                sql += frag
            params.extend(args)
        sql += " GROUP BY s.site_id"
        return self.conn.execute(sql, params).fetchone()

    def _resolve_client_id(self, client_code: str | None) -> int | None:
        """Résout l'identifiant du client rattaché (FK sites.client_id).

        - client_code fourni → client correspondant.
        - Sinon → client par défaut (premier de la table), jamais None tant
          qu'un client existe (la colonne client_id est NOT NULL).
        """
        if client_code:
            row = self.conn.execute(
                "SELECT id FROM clients WHERE code_client = %s",
                (client_code,),
            ).fetchone()
            if row:
                return row["id"]
        row = self.conn.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()
        return row["id"] if row else None

    def create_site(self, data: SiteCreate, admin_user_id: int, scope=None) -> dict:
        existing = self.conn.execute(
            "SELECT site_id FROM sites WHERE code = %s",
            (data.code,),
        ).fetchone()
        if existing:
            raise ValueError("Ce code de site existe déjà.")

        if isinstance(scope, list):
            requested = (data.client_code or "").strip()
            if not requested or requested not in scope:
                raise ValueError("Le code client doit faire partie de vos clients assignés.")
            client_code = requested
        else:
            client_code = scope if scope is not None else (data.client_code or None)

        client_id = self._resolve_client_id(client_code)
        row = self.conn.execute(
            """
            INSERT INTO sites (code, name, address, description, is_active, client_code, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING site_id
            """,
            (data.code, data.name, data.address, data.description, data.is_active,
             client_code, client_id),
        ).fetchone()
        site_id = row["site_id"]

        log_action(
            self.conn, admin_user_id, "site_create",
            "site", None,
            f"Création du site {data.code}" + (f" (client {client_code})" if client_code else ""),
        )
        return self.get_site(site_id)

    def update_site(self, site_id: int, data: SiteUpdate, admin_user_id: int, scope=None) -> dict:
        site = self.get_site(site_id, scope)
        if not site:
            raise ValueError("Site introuvable.")

        if data.code != site["code"]:
            existing = self.conn.execute(
                "SELECT site_id FROM sites WHERE code = %s AND site_id != %s",
                (data.code, site_id),
            ).fetchone()
            if existing:
                raise ValueError("Ce code de site existe déjà.")

        client_code = site["client_code"] if scope is not None else (data.client_code or None)
        client_id = self._resolve_client_id(client_code)

        self.conn.execute(
            """
            UPDATE sites
            SET code = %s, name = %s, address = %s, description = %s, is_active = %s,
                client_code = %s, client_id = %s, updated_at = %s
            WHERE site_id = %s
            """,
            (data.code, data.name, data.address, data.description, data.is_active,
             client_code, client_id, datetime.now(timezone.utc), site_id),
        )
        log_action(
            self.conn, admin_user_id, "site_update",
            "site", site_id,
            f"Modification du site {data.code}",
        )
        return self.get_site(site_id)

    def delete_site(self, site_id: int, admin_user_id: int, scope=None) -> None:
        site = self.get_site(site_id, scope)
        if not site:
            raise ValueError("Site introuvable.")

        post_count = site.get("post_count") or 0
        if post_count > 0:
            raise ValueError(f"Impossible de supprimer ce site car il contient {post_count} poste(s).")

        self.conn.execute("DELETE FROM sites WHERE site_id = %s", (site_id,))
        log_action(
            self.conn, admin_user_id, "site_delete",
            "site", site_id,
            f"Suppression du site {site['code']}",
        )


class PostService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def list_posts(self, site_id: int | None = None, search: str | None = None,
                   scope=None) -> list[dict]:
        sql = """
            SELECT p.*, s.name AS site_name
            FROM posts p
            LEFT JOIN sites s ON s.site_id = p.site_id
        """
        clauses = []
        params = []
        if site_id:
            clauses.append("p.site_id = %s")
            params.append(site_id)
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "s.client_code")
            if frag:
                clauses.append(frag.lstrip(" AND "))
            params.extend(args)
        if search:
            term = f"%{search}%"
            clauses.append("(p.code ILIKE %s OR p.name ILIKE %s)")
            params.extend([term, term])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY p.code"
        return self.conn.execute(sql, params).fetchall()

    def get_post(self, post_id: int, scope=None) -> dict | None:
        sql = """
            SELECT p.*, s.name AS site_name
            FROM posts p
            LEFT JOIN sites s ON s.site_id = p.site_id
            WHERE p.post_id = %s
        """
        params = [post_id]
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "s.client_code")
            if frag:
                sql += frag
            params.extend(args)
        return self.conn.execute(sql, params).fetchone()

    def create_post(self, data: PostCreate, admin_user_id: int, scope=None) -> dict:
        site = self.conn.execute(
            "SELECT site_id, client_code FROM sites WHERE site_id = %s",
            (data.site_id,),
        ).fetchone()
        if not site:
            raise ValueError("Le site sélectionné n'existe pas.")
        if scope is not None and not site_in_scope(scope, site["client_code"]):
            raise ValueError("Le site sélectionné n'existe pas.")

        existing = self.conn.execute(
            "SELECT post_id FROM posts WHERE code = %s",
            (data.code,),
        ).fetchone()
        if existing:
            raise ValueError("Ce code de poste existe déjà.")

        row = self.conn.execute(
            """
            INSERT INTO posts (site_id, code, name, player_type, ip_address, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING post_id
            """,
            (data.site_id, data.code, data.name, data.player_type, data.ip_address, data.is_active),
        ).fetchone()
        post_id = row["post_id"]

        log_action(
            self.conn, admin_user_id, "post_create",
            "post", None,
            f"Création du poste {data.code}",
        )
        return self.get_post(post_id)

    def update_post(self, post_id: int, data: PostUpdate, admin_user_id: int, scope=None) -> dict:
        post = self.get_post(post_id, scope)
        if not post:
            raise ValueError("Poste introuvable.")

        if scope is not None:
            target = self.conn.execute(
                "SELECT client_code FROM sites WHERE site_id = %s",
                (data.site_id,),
            ).fetchone()
            if not target or not site_in_scope(scope, target["client_code"]):
                raise ValueError("Le site sélectionné n'existe pas.")

        if data.code != post["code"]:
            existing = self.conn.execute(
                "SELECT post_id FROM posts WHERE code = %s AND post_id != %s",
                (data.code, post_id),
            ).fetchone()
            if existing:
                raise ValueError("Ce code de poste existe déjà.")

        self.conn.execute(
            """
            UPDATE posts
            SET site_id = %s, code = %s, name = %s, player_type = %s, ip_address = %s,
                is_active = %s, updated_at = %s
            WHERE post_id = %s
            """,
            (data.site_id, data.code, data.name, data.player_type, data.ip_address,
             data.is_active, datetime.now(timezone.utc), post_id),
        )
        log_action(
            self.conn, admin_user_id, "post_update",
            "post", post_id,
            f"Modification du poste {data.code}",
        )
        return self.get_post(post_id)

    def delete_post(self, post_id: int, admin_user_id: int, scope=None) -> None:
        post = self.get_post(post_id, scope)
        if not post:
            raise ValueError("Poste introuvable.")

        self.conn.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
        log_action(
            self.conn, admin_user_id, "post_delete",
            "post", post_id,
            f"Suppression du poste {post['code']}",
        )

    def batch_assign_media(self, data: BatchAssignMediaRequest, admin_user_id: int,
                           scope=None) -> dict:
        self._assert_zone_allowed(admin_user_id, data.zone_number)

        success = []
        failed = []

        for post_id in data.post_ids:
            post = self.conn.execute(
                """
                SELECT p.post_id, s.client_code
                FROM posts p
                LEFT JOIN sites s ON s.site_id = p.site_id
                WHERE p.post_id = %s
                """,
                (post_id,),
            ).fetchone()
            if not post or (scope is not None and not site_in_scope(scope, post["client_code"])):
                failed.append(post_id)
                continue

            media = self.conn.execute(
                "SELECT media_id, client_code FROM media WHERE media_id = %s",
                (data.media_id,),
            ).fetchone()
            if not media or (scope is not None and not site_in_scope(scope, media["client_code"])):
                failed.append(post_id)
                continue

            existing = self.conn.execute(
                """
                SELECT zone_media_id FROM zone_media
                WHERE post_id = %s AND zone_number = %s
                """,
                (post_id, data.zone_number),
            ).fetchone()

            if existing:
                self.conn.execute(
                    "UPDATE zone_media SET media_id = %s, updated_at = %s WHERE zone_media_id = %s",
                    (data.media_id, datetime.now(timezone.utc), existing["zone_media_id"]),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO zone_media (post_id, zone_number, media_id, display_order, is_active)
                    VALUES (%s, %s, %s, 1, TRUE)
                    """,
                    (post_id, data.zone_number, data.media_id),
                )

            success.append(post_id)

        if success:
            log_action(
                self.conn, admin_user_id, "batch_assign_media",
                "zone_media", None,
                f"Affectation du média {data.media_id} à {len(success)} poste(s)",
            )

        return {"success_count": len(success), "failed_ids": failed}

    def _assert_zone_allowed(self, user_id: int, zone_number: int) -> None:
        """Vérifie qu'un utilisateur non administrateur a le droit d'affecter un média sur cette zone."""
        assert_zone_allowed(self.conn, user_id, zone_number)


class GroupService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def _savepoint_exec(self, savepoint: str, sql: str, params, purpose: str, ctx: dict) -> bool:
        """Exécute une opération isolée dans un SAVEPOINT.

        Si l'opération échoue, le SAVEPOINT est annulé (ROLLBACK TO + RELEASE)
        et l'erreur est loguée à niveau error avec les identifiants concernés :
        le reste de la transaction reste valide et commitable. S'applique aux
        opérations "best effort" dont l'échec ne doit pas empoisonner la
        transaction (même famille que le bug silencieux de sync : une exception
        avalée sans rollback laisse une transaction abattue et un commit perdu).
        Retourne True si l'opération a réussi.
        """
        self.conn.execute(f"SAVEPOINT {savepoint}")
        try:
            self.conn.execute(sql, params)
        except Exception as exc:
            try:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                self.conn.rollback()
                raise
            fields = ", ".join(f"{k}={v}" for k, v in ctx.items())
            logger.error(
                "ROLLBACK SAVEPOINT %s — %s (%s, %s) : %s",
                savepoint, purpose, fields,
                datetime.now(timezone.utc).isoformat(), exc,
            )
            return False
        else:
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            return True

    def list_groups(self, allowed_group_ids: set[int] | None = None) -> list[dict]:
        sql = """
            SELECT g.group_id, g.name, g.description, g.is_active, g.created_at, g.updated_at,
                   COUNT(sgp.group_post_id) AS post_count
            FROM screen_groups g
            LEFT JOIN screen_group_posts sgp ON sgp.group_id = g.group_id
        """
        params = []
        if allowed_group_ids is not None:
            sql += " WHERE g.group_id = ANY(%s)"
            params.append(list(allowed_group_ids))
        sql += " GROUP BY g.group_id ORDER BY g.name"
        return self.conn.execute(sql, params).fetchall()

    def get_group(self, group_id: int) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM screen_groups WHERE group_id = %s",
            (group_id,),
        ).fetchone()

    def create_group(self, data: GroupCreate, admin_user_id: int,
                    assign_to_user: int | None = None) -> dict:
        row = self.conn.execute(
            """
            INSERT INTO screen_groups (name, description, is_active)
            VALUES (%s, %s, %s)
            RETURNING group_id
            """,
            (data.name, data.description, data.is_active),
        ).fetchone()
        group_id = row["group_id"]
        if assign_to_user:
            self.conn.execute(
                "INSERT INTO user_group_access (user_id, group_id, is_allowed) VALUES (%s, %s, TRUE)",
                (assign_to_user, group_id),
            )
        log_action(
            self.conn, admin_user_id, "group_create",
            "screen_group", None,
            f"Création du groupe {data.name}",
        )
        return self.get_group(group_id)

    def update_group(self, group_id: int, data: GroupUpdate, admin_user_id: int) -> dict:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Groupe introuvable.")

        self.conn.execute(
            """
            UPDATE screen_groups
            SET name = %s, description = %s, is_active = %s, updated_at = %s
            WHERE group_id = %s
            """,
            (data.name, data.description, data.is_active, datetime.now(timezone.utc), group_id),
        )
        log_action(
            self.conn, admin_user_id, "group_update",
            "screen_group", group_id,
            f"Modification du groupe {data.name}",
        )
        return self.get_group(group_id)

    def delete_group(self, group_id: int, admin_user_id: int) -> None:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Groupe introuvable.")

        self.conn.execute("DELETE FROM screen_group_posts WHERE group_id = %s", (group_id,))
        self.conn.execute("DELETE FROM user_group_access WHERE group_id = %s", (group_id,))
        self.conn.execute("DELETE FROM screen_groups WHERE group_id = %s", (group_id,))
        log_action(
            self.conn, admin_user_id, "group_delete",
            "screen_group", group_id,
            f"Suppression du groupe {group['name']}",
        )

    def get_group_posts(self, group_id: int, scope=None) -> list[dict]:
        sql = """
            SELECT p.post_id, p.code, p.name, s.name AS site_name
            FROM posts p
            JOIN screen_group_posts sgp ON sgp.post_id = p.post_id
            LEFT JOIN sites s ON s.site_id = p.site_id
            WHERE sgp.group_id = %s
        """
        params = [group_id]
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "s.client_code")
            if frag:
                sql += frag
            params.extend(args)
        sql += " ORDER BY p.code"
        return self.conn.execute(sql, params).fetchall()

    def _scoped_post_ids(self, post_ids: list[int], scope) -> list[int]:
        if not post_ids:
            return []
        if scope is None:
            return list(post_ids)
        sql = """
            SELECT p.post_id
            FROM posts p
            LEFT JOIN sites s ON s.site_id = p.site_id
            WHERE p.post_id = ANY(%s)
        """
        params = [list(post_ids)]
        frag, args = scope_sql(scope, "s.client_code")
        if frag:
            sql += frag
        params.extend(args)
        rows = self.conn.execute(sql, params).fetchall()
        return [r["post_id"] for r in rows]

    def add_posts_to_group(self, group_id: int, post_ids: list[int], admin_user_id: int,
                           scope=None) -> None:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Groupe introuvable.")

        existing_ids = {
            r["post_id"]
            for r in self.conn.execute(
                "SELECT post_id FROM screen_group_posts WHERE group_id = %s",
                (group_id,),
            ).fetchall()
        }

        added = 0
        for pid in self._scoped_post_ids(post_ids, scope):
            if pid in existing_ids:
                continue
            self.conn.execute(
                "INSERT INTO screen_group_posts (group_id, post_id) VALUES (%s, %s)",
                (group_id, pid),
            )
            added += 1

        if added:
            log_action(
                self.conn, admin_user_id, "group_add_posts",
                "screen_group", group_id,
                f"Ajout de {added} poste(s) au groupe {group['name']}",
            )

    def remove_posts_from_group(self, group_id: int, post_ids: list[int], admin_user_id: int,
                                scope=None) -> None:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Groupe introuvable.")

        scoped = self._scoped_post_ids(post_ids, scope)
        if not scoped:
            return

        cur = self.conn.execute(
            "DELETE FROM screen_group_posts WHERE group_id = %s AND post_id = ANY(%s)",
            (group_id, scoped),
        )

        if cur.rowcount:
            log_action(
                self.conn, admin_user_id, "group_remove_posts",
                "screen_group", group_id,
                f"Retrait de {cur.rowcount} poste(s) du groupe {group['name']}",
            )

    def set_group_membership(self, group_id: int, post_ids: list[int], admin_user_id: int,
                             scope=None) -> dict:
        """Remplace l'ensemble des postes du groupe (idempotent, sans doublon).

        Les postes non listés sont retirés ; les postes listés sont ajoutés.
        Pour un client (scope), seuls ses propres postes peuvent être gérés.
        Retourne le décompte final par site pour la composition.
        """
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Groupe introuvable.")

        wanted = set(int(p) for p in post_ids if p is not None)
        if scope is not None:
            wanted = set(self._scoped_post_ids(sorted(wanted), scope))

        current = {
            r["post_id"]
            for r in self.conn.execute(
                "SELECT post_id FROM screen_group_posts WHERE group_id = %s",
                (group_id,),
            ).fetchall()
        }

        to_add = wanted - current
        to_remove = current - wanted
        if scope is not None:
            current_scoped = set(self._scoped_post_ids(sorted(current), scope))
            to_remove = current_scoped - wanted
            to_add = wanted - current_scoped

        if to_remove:
            self.conn.execute(
                "DELETE FROM screen_group_posts WHERE group_id = %s AND post_id = ANY(%s)",
                (group_id, list(to_remove)),
            )

        if to_add:
            for pid in to_add:
                # Échec isolé (ex. doublon de course sur uq_group_post) : on ne
                # touche pas au reste de la transaction (voir _savepoint_exec).
                self._savepoint_exec(
                    "group_membership_sp",
                    "INSERT INTO screen_group_posts (group_id, post_id) VALUES (%s, %s)",
                    (group_id, pid),
                    "ajout d'un poste au groupe",
                    {"group_id": group_id, "post_id": pid},
                )

        log_action(
            self.conn, admin_user_id, "group_set_membership",
            "screen_group", group_id,
            f"Composition du groupe {group['name']} à jour : {len(wanted)} poste(s).",
        )

        return self.get_group_composition(group_id, scope)

    def get_group_composition(self, group_id: int, scope=None) -> dict | None:
        """Retourne le groupe avec ses sites et les postes (avec appartenance)."""
        group = self.get_group(group_id)
        if not group:
            return None

        member_posts = {
            r["post_id"]
            for r in self.conn.execute(
                "SELECT post_id FROM screen_group_posts WHERE group_id = %s",
                (group_id,),
            ).fetchall()
        }

        sites_sql = "SELECT s.site_id, s.code, s.name FROM sites s WHERE s.is_active = TRUE"
        params = []
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "s.client_code")
            if frag:
                sites_sql += frag
            params.extend(args)
        sites_sql += " ORDER BY s.name"

        sites = self.conn.execute(sites_sql, params).fetchall()

        for site in sites:
            site["posts"] = self.conn.execute(
                """
                SELECT p.post_id, p.code, p.name, p.site_id
                FROM posts p
                WHERE p.site_id = %s AND p.is_active = TRUE
                ORDER BY p.name
                """,
                (site["site_id"],),
            ).fetchall()

        if scope:
            member_posts = set(self._scoped_post_ids(sorted(member_posts), scope))

        return {
            "group_id": group["group_id"],
            "name": group["name"],
            "description": group["description"],
            "is_active": group["is_active"],
            "post_count": len(member_posts),
            "sites": [
                {
                    "site_id": s["site_id"],
                    "code": s["code"],
                    "name": s["name"],
                    "posts": [
                        {"post_id": p["post_id"], "code": p["code"], "name": p["name"], "in_group": p["post_id"] in member_posts}
                        for p in s["posts"]
                    ],
                }
                for s in sites
            ],
        }

    def group_post_ids(self, group_id: int) -> list[int]:
        """Liste des post_id appartenant au groupe, dans un ordre stable."""
        rows = self.conn.execute(
            "SELECT post_id FROM screen_group_posts WHERE group_id = %s ORDER BY post_id",
            (group_id,),
        ).fetchall()
        return [r["post_id"] for r in rows]

    def apply_configuration_to_group(
        self,
        group_id: int,
        data,
        admin_user_id: int,
        scope=None,
    ) -> dict:
        """Applique une configuration d'affichage à tous les postes du groupe.

        Pour chaque poste du groupe :
          1. enregistre la configuration (layout, zones/médias) via ConfigurationService,
          2. si ``sync`` est vrai, soumet un job de synchronisation SFTP à
             l'executor borné (SyncService) — jamais un thread brut.

        Retourne les décomptes. Les postes hors groupe ne sont jamais modifiés.
        """
        from app.schemas.configuration import PostConfigurationUpdate, ZoneMediaAssignment
        from app.services.configuration_service import ConfigurationService
        from app.services.sync_service import SyncService

        group = self.get_group(group_id)
        if not group:
            raise ValueError("Groupe introuvable.")

        post_ids = self.group_post_ids(group_id)
        if scope is not None:
            post_ids = self._scoped_post_ids(post_ids, scope)
        if not post_ids:
            raise ValueError("Le groupe ne contient aucun poste.")

        config_svc = ConfigurationService(self.conn)
        payload = PostConfigurationUpdate(
            layout_id=data.layout_id,
            loop_enabled=data.loop_enabled,
            schedule_enabled=data.schedule_enabled,
            display_enabled=data.display_enabled,
            zones=[ZoneMediaAssignment(**z) for z in data.zones],
        )

        success_ids = []
        failed_ids = []
        synced_ids = []

        for pid in post_ids:
            # Isolation par poste : une config qui échoue (ex. média disparu,
            # donnée invalide) est repliée sans empoisonner les postes suivants.
            # Sans ce SAVEPOINT, une écriture partielle restait dans la
            # transaction (succès comptabilisé à tort) ou un échec DB déclenchait
            # une transaction abattue pour tout le groupe (500 + liste erronée).
            savepoint = "apply_config_sp"
            self.conn.execute(f"SAVEPOINT {savepoint}")
            try:
                config_svc.update_configuration(pid, payload, user_id=admin_user_id)
            except Exception as exc:
                try:
                    self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                except Exception:
                    self.conn.rollback()
                    raise
                logger.error(
                    "ROLLBACK SAVEPOINT apply_config_sp — configuration du poste "
                    "impossible (group_id=%s post_id=%s, %s) : %s",
                    group_id, pid, datetime.now(timezone.utc).isoformat(), exc,
                )
                failed_ids.append(pid)
            else:
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                success_ids.append(pid)

        if data.sync:
            sync_svc = SyncService(self.conn)
            from app.services.sync_executor import sync_executor

            for pid in success_ids:
                if sync_svc.check_running_sync(pid):
                    continue
                # Échec isolé de création de job : le poste est remonté en échec
                # mais la suite (et la liste des échecs) reste exploitable.
                self.conn.execute("SAVEPOINT sync_job_sp")
                try:
                    job = sync_svc.create_job(pid, None)
                except Exception as exc:
                    try:
                        self.conn.execute("ROLLBACK TO SAVEPOINT sync_job_sp")
                        self.conn.execute("RELEASE SAVEPOINT sync_job_sp")
                    except Exception:
                        self.conn.rollback()
                        raise
                    logger.error(
                        "ROLLBACK SAVEPOINT sync_job_sp — création du job de sync "
                        "impossible (group_id=%s post_id=%s, %s) : %s",
                        group_id, pid, datetime.now(timezone.utc).isoformat(), exc,
                    )
                    failed_ids.append(pid)
                    continue
                else:
                    self.conn.execute(f"RELEASE SAVEPOINT sync_job_sp")
                job_id = job["sync_job_id"]
                try:
                    # Exécution bornée : le job passe par l'executor commun
                    # (threads <= SYNC_MAX_WORKERS, connexions via le pool
                    # dédié gesto-sync) au lieu d'un thread brute.
                    sync_executor.submit(pid, job_id)
                except Exception as exc:
                    # Le job existe mais ne tournera jamais : le marquer en échec
                    # évite un job orphelin de plus, et le rendre visible.
                    sync_svc.mark_job_failed(
                        job_id,
                        f"Échec de la soumission à l'executor de sync (group_id={group_id}) : {exc}",
                    )
                    logger.error(
                        "Soumission à l'executor de sync impossible (group_id=%s post_id=%s "
                        "job_id=%s, %s) : %s",
                        group_id, pid, job_id, datetime.now(timezone.utc).isoformat(), exc,
                    )
                    failed_ids.append(pid)
                    continue
                synced_ids.append(pid)

        return {
            "group_id": group_id,
            "success_count": len(success_ids),
            "failed_post_ids": sorted(set(failed_ids)),
            "synced_post_ids": sorted(synced_ids),
        }


class MediaService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def list_media(self, media_type: str | None = None, scope=None) -> list[dict]:
        sql = "SELECT * FROM media WHERE is_active = TRUE"
        params = []
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "client_code")
            if frag:
                sql += frag
            params.extend(args)
        if media_type:
            sql += " AND media_type = %s"
            params.append(media_type.upper())
        sql += " ORDER BY created_at DESC"
        return self.conn.execute(sql, params).fetchall()

    def get_media(self, media_id: int, scope=None) -> dict | None:
        sql = "SELECT * FROM media WHERE media_id = %s AND is_active = TRUE"
        params = [media_id]
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "client_code")
            if frag:
                sql += frag
            params.extend(args)
        return self.conn.execute(sql, params).fetchone()

    def delete_media(self, media_id: int, admin_user_id: int, scope=None) -> None:
        media = self.conn.execute(
            "SELECT * FROM media WHERE media_id = %s",
            (media_id,),
        ).fetchone()
        if not media or (scope is not None and not site_in_scope(scope, media["client_code"])):
            raise ValueError("Média introuvable.")

        usage = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM zone_media WHERE media_id = %s",
            (media_id,),
        ).fetchone()
        if usage["cnt"] and usage["cnt"] > 0:
            raise ValueError("Ce média est utilisé dans une configuration de poste.")

        if media["sftp_path"]:
            root = settings.SFTP_ROOT_PATH.rstrip("/")
            with SFTPClient() as sftp:
                sftp.remove_file(f"{root}/{media['sftp_path']}")

        self.conn.execute("DELETE FROM media WHERE media_id = %s", (media_id,))
        log_action(
            self.conn, admin_user_id, "media_delete",
            "media", media_id,
            f"Suppression du média {media['name']}",
        )