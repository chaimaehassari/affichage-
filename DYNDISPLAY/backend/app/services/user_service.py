from datetime import datetime, timedelta, timezone

from psycopg import Connection

from app.core.security import hash_password, verify_password
from app.schemas.auth import (
    UserCreateRequest,
    UserUpdateRequest,
)
from app.services.audit_service import log_action

MAX_PASSWORD_HISTORY = 3
PASSWORD_EXPIRY_MONTHS = 3
MAX_FAILED_ATTEMPTS = 3
LOCKOUT_MINUTES = 15


class UserService:
    def __init__(self, conn: Connection):
        self.conn = conn

    # --- List users ---

    def list_users(self, search: str | None = None) -> list[dict]:
        sql = """
            SELECT u.user_id, u.user_code, u.login, u.email, u.profile_id, u.is_active,
                   u.is_activated, u.sites_limit, u.posts_limit, u.activated_at,
                   u.created_at, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
        """
        params = []
        if search:
            term = f"%{search}%"
            sql += " WHERE (u.login ILIKE %s OR u.user_code ILIKE %s OR u.user_id::text ILIKE %s)"
            params = [term, term, term]
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

    # --- Create user ---

    def create_user(self, data: UserCreateRequest, admin_user_id: int) -> dict:
        existing = self.get_user_by_login(data.login)
        if existing:
            raise ValueError("Ce login existe déjà.")

        if data.email:
            existing_email = self.get_user_by_email(data.email)
            if existing_email:
                raise ValueError("Cette adresse e-mail est déjà utilisée.")

        if data.user_code:
            existing_code = self.conn.execute(
                "SELECT user_id FROM users WHERE user_code = %s",
                (data.user_code,),
            ).fetchone()
            if existing_code:
                raise ValueError("Ce code utilisateur existe déjà.")

        if data.login == data.password:
            raise ValueError("Le login et le mot de passe doivent être différents.")

        password_hash = hash_password(data.password)
        row = self.conn.execute(
            """
            INSERT INTO users (profile_id, user_code, login, email, password_hash,
                               is_active, must_change_password, is_activated)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING user_id
            """,
            (data.profile_id, data.user_code or None, data.login, data.email or None,
             password_hash, data.is_active, not data.requires_activation),
        ).fetchone()
        user_id = row["user_id"]

        self._save_zones(user_id, data.zones)
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
            existing_code = self.conn.execute(
                "SELECT user_id FROM users WHERE user_code = %s AND user_id != %s",
                (data.user_code, user_id),
            ).fetchone()
            if existing_code:
                raise ValueError("Ce code utilisateur existe déjà.")

        self.conn.execute(
            """
            UPDATE users
            SET login = %s, profile_id = %s, user_code = %s, email = %s, is_active = %s,
                is_activated = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (data.login, data.profile_id, data.user_code or None, data.email or None,
             data.is_active, not data.requires_activation, datetime.now(timezone.utc), user_id),
        )

        self._save_zones(user_id, data.zones)
        self._save_permissions(user_id, data.permissions)

        if data.new_password:
            self._validate_password_history(user_id, data.new_password)
            password_hash = hash_password(data.new_password)
            self.conn.execute(
                """
                UPDATE users
                SET password_hash = %s, must_change_password = FALSE, failed_attempts = 0,
                    locked_until = NULL, last_password_change_at = %s, updated_at = %s
                WHERE user_id = %s
                """,
                (password_hash, datetime.now(timezone.utc), datetime.now(timezone.utc), user_id),
            )
            self._add_password_history(user_id, password_hash)
            self._trim_password_history(user_id)
            log_action(
                self.conn, admin_user_id, "password_change",
                "user", user_id,
                f"Changement du mot de passe de {data.login}",
            )

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
        self.conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        log_action(
            self.conn, admin_user_id, "user_delete",
            "user", user_id,
            f"Suppression de l'utilisateur {login}",
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