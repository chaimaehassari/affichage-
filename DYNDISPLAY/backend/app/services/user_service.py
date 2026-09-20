from datetime import datetime, timedelta, timezone

from psycopg import Connection

from app.core.security import hash_password, verify_password
from app.schemas.auth import (
    UserCreateRequest,
    UserUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.scope import scope_sql, site_in_scope

MAX_PASSWORD_HISTORY = 3
PASSWORD_EXPIRY_MONTHS = 3
MAX_FAILED_ATTEMPTS = 3
LOCKOUT_MINUTES = 15


class UserService:
    def __init__(self, conn: Connection):
        self.conn = conn

    # --- List users ---

    def list_users(self, search: str | None = None, scope=None, owner_user_id: int | None = None) -> list[dict]:
        sql = """
            SELECT u.user_id, u.user_code, u.login, u.email, u.profile_id, u.is_active,
                   u.is_activated, u.is_superadmin, u.sites_limit, u.posts_limit, u.activated_at,
                   u.created_at, p.name AS profile_name, u.admin_id,
                   COALESCE(
                     (SELECT adm.login FROM users adm WHERE adm.user_id = u.admin_id),
                     (SELECT adm2.login FROM admin_clients ac
                      JOIN users adm2 ON adm2.user_id = ac.admin_id
                      WHERE ac.client_code = u.user_code LIMIT 1)
                   ) AS admin_login,
                   COALESCE(
                     (SELECT adm3.user_code FROM users adm3 WHERE adm3.user_id = u.admin_id),
                     (SELECT adm4.user_code FROM admin_clients ac
                      JOIN users adm4 ON adm4.user_id = ac.admin_id
                      WHERE ac.client_code = u.user_code LIMIT 1)
                   ) AS admin_code,
                   (SELECT COALESCE(uu.login, '') FROM users uu
                    WHERE uu.user_code = u.user_code AND uu.user_code IS NOT NULL
                    ORDER BY uu.user_id LIMIT 1) AS client_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
        """
        params = []
        where = []
        if owner_user_id is not None:
            where.append("u.admin_id = %s")
            params.append(owner_user_id)
        elif scope is not None and scope != "":
            frag, args = scope_sql(scope, "u.user_code")
            if frag:
                where.append(frag.lstrip(" AND "))
            params.extend(args)
        if search:
            term = f"%{search}%"
            where.append("(u.login ILIKE %s OR u.user_code ILIKE %s OR u.user_id::text ILIKE %s)")
            params.extend([term, term, term])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY u.user_id"
        return self.conn.execute(sql, params).fetchall()

    def get_user(self, user_id: int) -> dict | None:
        return self.conn.execute(
            """
            SELECT u.*, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.user_id = %s
            """,
            (user_id,),
        ).fetchone()

    def get_user_by_login(self, login: str) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM users WHERE login = %s",
            (login,),
        ).fetchone()

    def get_user_by_email(self, email: str | None) -> dict | None:
        if not email:
            return None
        return self.conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        ).fetchone()

    def get_user_zones(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT zone_number, is_allowed FROM user_zone_access WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        return [
            {"zone_number": z["zone_number"], "is_allowed": z["is_allowed"]}
            for z in rows
        ]

    def get_user_permissions(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT p.permission_id, p.code, p.name, up.can_view, up.can_create,
                   up.can_update, up.can_delete
            FROM user_permissions up
            JOIN permissions p ON p.permission_id = up.permission_id
            WHERE up.user_id = %s
            """,
            (user_id,),
        ).fetchall()
        return [
            {
                "permission_id": p["permission_id"],
                "code": p["code"],
                "name": p["name"],
                "can_view": p["can_view"],
                "can_create": p["can_create"],
                "can_update": p["can_update"],
                "can_delete": p["can_delete"],
            }
            for p in rows
        ]

    def get_user_groups(self, user_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT group_id FROM user_group_access WHERE user_id = %s AND is_allowed = TRUE",
            (user_id,),
        ).fetchall()
        return [r["group_id"] for r in rows]

    # --- Create user ---

    def _default_client_id(self) -> int:
        """Client par défaut (premier client de la table)."""
        row = self.conn.execute(
            "SELECT id FROM clients ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            raise ValueError("Aucun client configuré : créez un client avant d'ajouter des comptes.")
        return row["id"]

    def _resolve_client_id(self, client_code: str | None) -> int:
        """Rattachement explicite d'un compte à un client.

        - user_code correspondant à un code_client → ce client ;
        - sinon → du Client par défaut (rattachement réel en base, jamais
          de compte « sans client »). Après migration 019, client_id NOT NULL.
        """
        if client_code:
            row = self.conn.execute(
                "SELECT id FROM clients WHERE code_client = %s",
                (client_code,),
            ).fetchone()
            if row:
                return row["id"]
        return self._default_client_id()

    def create_user(self, data: UserCreateRequest, admin_user_id: int) -> dict:
        existing = self.get_user_by_login(data.login)
        if existing:
            raise ValueError("Ce login existe déjà.")

        if data.email:
            existing_email = self.get_user_by_email(data.email)
            if existing_email:
                raise ValueError("Cette adresse e-mail est déjà utilisée.")

        if data.user_code:
            is_client_code = self.conn.execute(
                "SELECT 1 FROM clients WHERE code_client = %s",
                (data.user_code,),
            ).fetchone() is not None
            if not is_client_code:
                existing_code = self.conn.execute(
                    "SELECT user_id FROM users WHERE user_code = %s",
                    (data.user_code,),
                ).fetchone()
                if existing_code:
                    raise ValueError("Ce code utilisateur existe déjà.")

        if data.login == data.password:
            raise ValueError("Le login et le mot de passe doivent être différents.")

        if data.admin_id:
            admin_row = self.conn.execute(
                "SELECT user_id, profile_id FROM users WHERE user_id = %s",
                (data.admin_id,),
            ).fetchone()
            if not admin_row:
                raise ValueError("L'administrateur associé est introuvable.")
            admin_profile = self.conn.execute(
                "SELECT name FROM profiles WHERE profile_id = %s",
                (admin_row["profile_id"],),
            ).fetchone()
            if not admin_profile or admin_profile["name"] != "Administrateur":
                raise ValueError("Le code admin doit désigner un utilisateur de profil Administrateur.")

        password_hash = hash_password(data.password)
        from app.core.license_utils import generate_account_code
        account_code = generate_account_code()
        is_supreme = bool(getattr(data, "is_superadmin", False))
        client_id = self._resolve_client_id(data.user_code)
        row = self.conn.execute(
            """
            INSERT INTO users (profile_id, user_code, login, email, password_hash,
                               is_active, must_change_password, is_activated, is_superadmin,
                               account_code, requires_activation, admin_id, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s)
            RETURNING user_id
            """,
            (data.profile_id, data.user_code or None, data.login, data.email or None,
             password_hash, data.is_active, not data.requires_activation, is_supreme,
             account_code, not is_supreme,
             data.admin_id, client_id),
        ).fetchone()
        user_id = row["user_id"]

        self._save_zones(user_id, data.zones)
        self._save_groups(user_id, data.groups)
        self._save_permissions(user_id, data.permissions)

        log_action(
            self.conn, admin_user_id, "user_create",
            "user", user_id,
            f"Création de l'utilisateur {data.login}",
        )
        return self.get_user(user_id)

    # --- Update user ---

    def update_user(self, user_id: int, data: UserUpdateRequest, admin_user_id: int) -> dict:
        user = self.get_user(user_id)
        if not user:
            raise ValueError("Utilisateur introuvable.")

        if data.login != user["login"]:
            existing = self.get_user_by_login(data.login)
            if existing:
                raise ValueError("Ce login existe déjà.")

        if data.email and data.email != (user["email"] or "").lower():
            existing_email = self.get_user_by_email(data.email)
            if existing_email and existing_email["user_id"] != user_id:
                raise ValueError("Cette adresse e-mail est déjà utilisée.")

        if data.user_code and data.user_code != user["user_code"]:
            is_client_code = self.conn.execute(
                "SELECT 1 FROM clients WHERE code_client = %s",
                (data.user_code,),
            ).fetchone() is not None
            if not is_client_code:
                existing_code = self.conn.execute(
                    "SELECT user_id FROM users WHERE user_code = %s AND user_id != %s",
                    (data.user_code, user_id),
                ).fetchone()
                if existing_code:
                    raise ValueError("Ce code utilisateur existe déjà.")

        if data.admin_id:
            admin_row = self.conn.execute(
                "SELECT user_id, profile_id FROM users WHERE user_id = %s",
                (data.admin_id,),
            ).fetchone()
            if not admin_row:
                raise ValueError("L'administrateur associé est introuvable.")
            admin_profile = self.conn.execute(
                "SELECT name FROM profiles WHERE profile_id = %s",
                (admin_row["profile_id"],),
            ).fetchone()
            if not admin_profile or admin_profile["name"] != "Administrateur":
                raise ValueError("Le code admin doit désigner un utilisateur de profil Administrateur.")

        client_id = self._resolve_client_id(data.user_code)
        self.conn.execute(
            """
            UPDATE users
            SET login = %s, profile_id = %s, user_code = %s, email = %s, is_active = %s,
                is_activated = %s, admin_id = %s, client_id = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (data.login, data.profile_id, data.user_code or None, data.email or None,
             data.is_active, not data.requires_activation, data.admin_id, client_id,
             datetime.now(timezone.utc), user_id),
        )

        self._save_zones(user_id, data.zones)
        self._save_groups(user_id, data.groups)
        self._save_permissions(user_id, data.permissions)

        log_action(
            self.conn, admin_user_id, "user_update",
            "user", user_id,
            f"Modification de l'utilisateur {data.login}",
        )
        return self.get_user(user_id)

    # --- Delete user ---

    def delete_user(self, user_id: int, admin_user_id: int) -> None:
        user = self.get_user(user_id)
        if not user:
            raise ValueError("Utilisateur introuvable.")

        login = user["login"]
        self.conn.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM password_history WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM user_zone_access WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM user_group_access WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        log_action(
            self.conn, admin_user_id, "user_delete",
            "user", user_id,
            f"Suppression de l'utilisateur {login}",
        )

    # --- Admin management ---

    def get_admin_client_codes(self, user_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT client_code FROM admin_clients WHERE admin_id = %s ORDER BY client_code",
            (user_id,),
        ).fetchall()
        return [r["client_code"] for r in rows]

    def _save_admin_clients(self, user_id: int, client_codes: list[str]) -> None:
        self.conn.execute("DELETE FROM admin_clients WHERE admin_id = %s", (user_id,))
        seen = set()
        for code in client_codes or []:
            c = (code or "").strip().upper()
            if not c or c in seen:
                continue
            seen.add(c)
            self.conn.execute(
                "INSERT INTO admin_clients (admin_id, client_code) VALUES (%s, %s)",
                (user_id, c),
            )

    def list_admins(self) -> list[dict]:
        return self.conn.execute(
            """
            SELECT u.user_id, u.user_code, u.login, u.email, u.profile_id,
                   u.is_active, u.is_superadmin, u.created_at, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE p.name = 'Administrateur'
            ORDER BY u.is_superadmin DESC, u.user_id
            """
        ).fetchall()

    def get_admin(self, user_id: int) -> dict | None:
        return self.conn.execute(
            """
            SELECT u.user_id, u.user_code, u.login, u.email, u.profile_id,
                   u.is_active, u.is_superadmin, u.created_at, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.user_id = %s AND p.name = 'Administrateur'
            """,
            (user_id,),
        ).fetchone()

    def create_admin(self, data, admin_user_id: int) -> dict:
        existing = self.conn.execute(
            "SELECT user_id FROM users WHERE login = %s",
            (data.login,),
        ).fetchone()
        if existing:
            raise ValueError("Ce login existe déjà.")

        if data.user_code:
            existing_code = self.conn.execute(
                "SELECT user_id FROM users WHERE user_code = %s",
                (data.user_code,),
            ).fetchone()
            if existing_code:
                raise ValueError("Ce code administrateur existe déjà.")

        if data.login == data.password:
            raise ValueError("Le login et le mot de passe doivent être différents.")

        profile = self.conn.execute(
            "SELECT profile_id FROM profiles WHERE name = 'Administrateur'",
        ).fetchone()
        if not profile:
            raise ValueError("Profil Administrateur introuvable.")

        password_hash = hash_password(data.password)
        from app.core.license_utils import generate_account_code
        account_code = generate_account_code()
        is_supreme = bool(getattr(data, "is_superadmin", False))
        client_id = self._resolve_client_id(data.user_code)
        row = self.conn.execute(
            """
            INSERT INTO users (profile_id, user_code, login, email, password_hash,
                               is_active, must_change_password, is_activated, is_superadmin,
                               account_code, requires_activation, client_id)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s)
            RETURNING user_id
            """,
            (profile["profile_id"], data.user_code or None, data.login,
             data.email or None, password_hash, data.is_active, not is_supreme, is_supreme,
             account_code, not is_supreme, client_id),
        ).fetchone()
        user_id = row["user_id"]

        self._save_admin_clients(user_id, data.client_codes)

        log_action(
            self.conn, admin_user_id, "admin_create",
            "user", user_id,
            f"Création de l'admin {data.login}",
        )
        return self.get_admin(user_id)

    def update_admin(self, user_id: int, data, admin_user_id: int) -> dict:
        admin = self.get_admin(user_id)
        if not admin:
            raise ValueError("Admin introuvable.")

        if data.login != admin["login"]:
            existing = self.conn.execute(
                "SELECT user_id FROM users WHERE login = %s AND user_id != %s",
                (data.login, user_id),
            ).fetchone()
            if existing:
                raise ValueError("Ce login existe déjà.")

        if data.user_code and data.user_code != admin["user_code"]:
            existing_code = self.conn.execute(
                "SELECT user_id FROM users WHERE user_code = %s AND user_id != %s",
                (data.user_code, user_id),
            ).fetchone()
            if existing_code:
                raise ValueError("Ce code administrateur existe déjà.")

        if admin["is_superadmin"]:
            raise ValueError("Le Super Admin ne peut pas être modifié comme un Admin classique.")

        self.conn.execute(
            """
            UPDATE users
            SET login = %s, user_code = %s, email = %s, is_active = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (data.login, data.user_code or None, data.email or None,
             data.is_active, datetime.now(timezone.utc), user_id),
        )

        self._save_admin_clients(user_id, data.client_codes)

        log_action(
            self.conn, admin_user_id, "admin_update",
            "user", user_id,
            f"Modification de l'admin {data.login}",
        )
        return self.get_admin(user_id)

    def delete_admin(self, user_id: int, admin_user_id: int) -> None:
        admin = self.get_admin(user_id)
        if not admin:
            raise ValueError("Admin introuvable.")
        if admin["is_superadmin"]:
            raise ValueError("Le Super Admin ne peut pas être supprimé.")

        login = admin["login"]
        if user_id == admin_user_id:
            raise ValueError("Vous ne pouvez pas supprimer votre propre compte.")

        self.conn.execute("DELETE FROM admin_clients WHERE admin_id = %s", (user_id,))
        self.conn.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM password_history WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM user_zone_access WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM user_group_access WHERE user_id = %s", (user_id,))
        self.conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        log_action(
            self.conn, admin_user_id, "admin_delete",
            "user", user_id,
            f"Suppression de l'admin {login}",
        )

    def list_clients(self, scope=None) -> list[dict]:
        """Liste des clients (table `clients`) avec compteurs et licences.

        - scope None → tous les clients
        - scope liste → uniquement ces codes clients
        - scope str → uniquement ce code client
        """
        sql = """
            SELECT c.id, c.code_client, c.nom_client, c.created_at,
                   c.license_sites, c.license_posts,
                   (SELECT COUNT(*) FROM sites s WHERE s.client_id = c.id) AS site_count,
                   (SELECT COUNT(*) FROM users u
                     WHERE u.client_id = c.id) AS user_count,
                   (SELECT u.login FROM users u
                     WHERE u.client_id = c.id
                     ORDER BY u.user_id LIMIT 1) AS client_name
            FROM clients c
        """
        params = []
        if scope is not None and scope != "":
            frag, args = scope_sql(scope, "c.code_client")
            sql += " WHERE 1=1" + frag
            params.extend(args)
        sql += " ORDER BY c.code_client"
        rows = self.conn.execute(sql, params).fetchall()

        clients = []
        for row in rows:
            code = row["code_client"]
            admin_rows = self.conn.execute(
                """
                SELECT u.login AS admin_login, u.user_code AS admin_code
                FROM admin_clients ac
                JOIN users u ON u.user_id = ac.admin_id
                WHERE ac.client_code = %s
                ORDER BY u.login
                """,
                (code,),
            ).fetchall()
            clients.append({
                "client_id": row["id"],
                "client_code": code,
                "client_name": row["client_name"],
                "nom_client": row["nom_client"],
                "license_sites": row["license_sites"],
                "license_posts": row["license_posts"],
                "user_count": row["user_count"],
                "site_count": row["site_count"],
                "admin_login": admin_rows[0]["admin_login"] if admin_rows else None,
                "admin_code": admin_rows[0]["admin_code"] if admin_rows else None,
                "admins": [dict(ar) for ar in admin_rows],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            })
        return clients

    def get_client(self, client_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT c.id AS client_id, c.code_client, c.nom_client, c.created_at,
                   c.license_sites, c.license_posts,
                   (SELECT COUNT(*) FROM sites s WHERE s.client_id = c.id) AS site_count,
                   (SELECT COUNT(*) FROM users u
                     WHERE u.client_id = c.id) AS user_count,
                   (SELECT COUNT(*) FROM users u
                     WHERE u.client_id = c.id
                       AND u.requires_activation = FALSE
                       AND COALESCE(u.is_superadmin, FALSE) = FALSE) AS activated_count,
                   (SELECT u.login FROM users u
                     WHERE u.client_id = c.id
                     ORDER BY u.user_id LIMIT 1) AS client_name
            FROM clients c
            WHERE c.id = %s
            """,
            (client_id,),
        ).fetchone()
        if not row:
            return None
        client = dict(row)
        client["client_code"] = client["code_client"]
        admin_rows = self.conn.execute(
            """
            SELECT u.user_id, u.login, u.user_code
            FROM admin_clients ac
            JOIN users u ON u.user_id = ac.admin_id
            WHERE ac.client_code = %s
            ORDER BY u.login
            """,
            (client["code_client"],),
        ).fetchall()
        client["admins"] = [dict(ar) for ar in admin_rows]
        client["admin_login"] = admin_rows[0]["login"] if admin_rows else None
        client["admin_code"] = admin_rows[0]["user_code"] if admin_rows else None
        client["created_at"] = client["created_at"].isoformat() if client["created_at"] else None
        return client

    def get_client_by_code(self, client_code: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, code_client, nom_client FROM clients WHERE code_client = %s",
            (client_code,),
        ).fetchone()
        if not row:
            return None
        return self.get_client(row["id"])

    def update_client_license(
        self, client_id: int, license_sites: int, license_posts: int, admin_user_id: int
    ) -> dict:
        client = self.get_client(client_id)
        if not client:
            raise ValueError("Client introuvable.")
        self.conn.execute(
            """
            UPDATE clients
            SET license_sites = %s, license_posts = %s
            WHERE id = %s
            """,
            (license_sites, license_posts, client_id),
        )
        log_action(
            self.conn, admin_user_id, "client_license_update",
            "client", client_id,
            f"Licences du client {client['code_client']} : "
            f"{license_sites} sites / {license_posts} postes",
        )
        return self.get_client(client_id)

    def assign_admin_to_client(self, admin_id: int, client_code: str, admin_user_id: int) -> None:
        admin = self.get_admin(admin_id)
        if not admin:
            raise ValueError("Admin introuvable.")
        if admin["is_superadmin"]:
            raise ValueError("Le Super Admin gère déjà tous les clients.")
        client = self.conn.execute(
            "SELECT id FROM clients WHERE code_client = %s",
            (client_code,),
        ).fetchone()
        if not client:
            raise ValueError(f"Client {client_code} introuvable.")
        existing = self.conn.execute(
            "SELECT 1 FROM admin_clients WHERE admin_id = %s AND client_code = %s",
            (admin_id, client_code),
        ).fetchone()
        if existing:
            return
        self.conn.execute(
            "INSERT INTO admin_clients (admin_id, client_code) VALUES (%s, %s)",
            (admin_id, client_code),
        )
        log_action(
            self.conn, admin_user_id, "admin_client_assign",
            "user", admin_id,
            f"Affectation du client {client_code} à l'admin {admin['login']}",
        )

    def remove_admin_from_client(self, admin_id: int, client_code: str, admin_user_id: int) -> None:
        admin = self.get_admin(admin_id)
        if not admin:
            raise ValueError("Admin introuvable.")
        self.conn.execute(
            "DELETE FROM admin_clients WHERE admin_id = %s AND client_code = %s",
            (admin_id, client_code),
        )
        log_action(
            self.conn, admin_user_id, "admin_client_detach",
            "user", admin_id,
            f"Retrait du client {client_code} de l'admin {admin['login']}",
        )

# --- Reset password ---

    def reset_password(self, user_id: int, new_password: str, admin_user_id: int) -> None:
        user = self.get_user(user_id)
        if not user:
            raise ValueError("Utilisateur introuvable.")

        self._validate_password_history(user_id, new_password)

        password_hash = hash_password(new_password)
        self.conn.execute(
            """
            UPDATE users
            SET password_hash = %s, must_change_password = TRUE, failed_attempts = 0,
                locked_until = NULL, last_password_change_at = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (password_hash, datetime.now(timezone.utc), datetime.now(timezone.utc), user_id),
        )

        self._add_password_history(user_id, password_hash)
        self._trim_password_history(user_id)

        log_action(
            self.conn, admin_user_id, "password_reset",
            "user", user_id,
            f"Réinitialisation du mot de passe de {user['login']}",
        )

    # --- Password validation ---

    def _validate_password_history(self, user_id: int, new_password: str) -> None:
        history = self.conn.execute(
            """
            SELECT password_hash FROM password_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, MAX_PASSWORD_HISTORY),
        ).fetchall()
        for h in history:
            if verify_password(new_password, h["password_hash"]):
                raise ValueError(
                    f"Le mot de passe ne peut pas être réutilisé (parmi les {MAX_PASSWORD_HISTORY} derniers)."
                )

    def _add_password_history(self, user_id: int, password_hash: str) -> None:
        self.conn.execute(
            "INSERT INTO password_history (user_id, password_hash) VALUES (%s, %s)",
            (user_id, password_hash),
        )

    def _trim_password_history(self, user_id: int) -> None:
        self.conn.execute(
            """
            DELETE FROM password_history
            WHERE password_history_id IN (
                SELECT password_history_id FROM password_history
                WHERE user_id = %s
                ORDER BY created_at DESC
                OFFSET %s
            )
            """,
            (user_id, MAX_PASSWORD_HISTORY),
        )

    # --- Zones & permissions ---

    def _save_zones(self, user_id: int, zones: list[int]) -> None:
        self.conn.execute("DELETE FROM user_zone_access WHERE user_id = %s", (user_id,))
        for zone_num in zones:
            if 1 <= zone_num <= 8:
                self.conn.execute(
                    "INSERT INTO user_zone_access (user_id, zone_number, is_allowed) VALUES (%s, %s, TRUE)",
                    (user_id, zone_num),
                )

    def _save_groups(self, user_id: int, groups: list[int]) -> None:
        self.conn.execute("DELETE FROM user_group_access WHERE user_id = %s", (user_id,))
        for group_id in groups:
            if not group_id:
                continue
            self.conn.execute(
                "INSERT INTO user_group_access (user_id, group_id, is_allowed) VALUES (%s, %s, TRUE)",
                (user_id, group_id),
            )

    def _save_permissions(self, user_id: int, permissions: list[dict]) -> None:
        self.conn.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))
        for perm_data in permissions:
            perm_id = perm_data.get("permission_id")
            if not perm_id:
                continue
            self.conn.execute(
                """
                INSERT INTO user_permissions (user_id, permission_id, can_view, can_create, can_update, can_delete)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    perm_id,
                    perm_data.get("can_view", False),
                    perm_data.get("can_create", False),
                    perm_data.get("can_update", False),
                    perm_data.get("can_delete", False),
                ),
            )

    # --- Account lock ---

    def handle_failed_login(self, login: str) -> None:
        user = self.conn.execute(
            "SELECT user_id, failed_attempts FROM users WHERE login = %s",
            (login,),
        ).fetchone()
        if not user:
            return

        failed_attempts = (user["failed_attempts"] or 0) + 1
        locked_until = None
        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            log_action(
                self.conn, user["user_id"], "account_lock",
                "user", user["user_id"],
                f"Compte verrouillé après {MAX_FAILED_ATTEMPTS} tentatives échouées",
            )

        self.conn.execute(
            "UPDATE users SET failed_attempts = %s, locked_until = %s WHERE user_id = %s",
            (failed_attempts, locked_until, user["user_id"]),
        )

    def get_profiles(self) -> list[dict]:
        return self.conn.execute(
            "SELECT profile_id, name, description, is_active FROM profiles WHERE is_active = TRUE ORDER BY profile_id"
        ).fetchall()

    def get_all_permissions(self) -> list[dict]:
        return self.conn.execute(
            "SELECT permission_id, code, name, description, is_active FROM permissions WHERE is_active = TRUE ORDER BY permission_id"
        ).fetchall()