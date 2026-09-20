from datetime import datetime, timedelta, timezone

from psycopg import Connection

from app.core.security import create_access_token, verify_password
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo

MAX_ACTIVITY_IDLE_DAYS = 60
PASSWORD_MAX_AGE_DAYS = 90


def _build_user_info(conn: Connection, user_row: dict) -> UserInfo:
    permissions = []
    perms = conn.execute(
        """
        SELECT p.permission_id, p.code, p.name, up.can_view, up.can_create,
               up.can_update, up.can_delete
        FROM user_permissions up
        JOIN permissions p ON p.permission_id = up.permission_id
        WHERE up.user_id = %s AND p.is_active = TRUE
        """,
        (user_row["user_id"],),
    ).fetchall()
    for p in perms:
        permissions.append({
            "permission_id": p["permission_id"],
            "code": p["code"],
            "name": p["name"],
            "can_view": p["can_view"],
            "can_create": p["can_create"],
            "can_update": p["can_update"],
            "can_delete": p["can_delete"],
        })

    zones = [
        z["zone_number"]
        for z in conn.execute(
            "SELECT zone_number FROM user_zone_access WHERE user_id = %s AND is_allowed = TRUE",
            (user_row["user_id"],),
        ).fetchall()
    ]

    groups = [
        r["group_id"]
        for r in conn.execute(
            "SELECT group_id FROM user_group_access WHERE user_id = %s AND is_allowed = TRUE",
            (user_row["user_id"],),
        ).fetchall()
    ]

    return UserInfo(
        user_id=user_row["user_id"],
        login=user_row["login"],
        email=user_row.get("email"),
        is_active=user_row["is_active"],
        must_change_password=user_row["must_change_password"],
        profile_name=user_row.get("profile_name") or "",
        profile_id=user_row["profile_id"],
        permissions=permissions,
        zones=zones,
        groups=groups,
        user_code=user_row.get("user_code"),
        is_activated=bool(user_row.get("is_activated", True)),
        is_superadmin=bool(user_row.get("is_superadmin", False)),
        sites_limit=user_row.get("sites_limit"),
        posts_limit=user_row.get("posts_limit"),
        activated_at=user_row["activated_at"].isoformat() if user_row.get("activated_at") else None,
        requires_activation=bool(user_row.get("requires_activation", False)),
        account_code=user_row.get("account_code"),
        authorized_device_id=user_row.get("authorized_device_id"),
    )


class AuthService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def authenticate_user(self, data: LoginRequest) -> LoginResponse | None:
        user = self.conn.execute(
            """
            SELECT u.*, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.login = %s
            """,
            (data.login,),
        ).fetchone()
        if not user:
            return None

        if not user["is_active"]:
            return None

        if user["suspended_at"] is not None:
            return None

        if user["locked_until"] and user["locked_until"] > datetime.now(timezone.utc):
            return None

        if not verify_password(data.password, user["password_hash"]):
            return None

        profile_name = user.get("profile_name") or ""
        if profile_name != "Administrateur":
            expected_code = (user.get("user_code") or "").strip().lower()
            provided_code = (data.client_code or "").strip().lower()
            if not expected_code or provided_code != expected_code:
                return None

        now = datetime.now(timezone.utc)

        activity_ref = user["last_login_at"] or user["created_at"]
        if activity_ref is None or (now - activity_ref) > timedelta(days=MAX_ACTIVITY_IDLE_DAYS):
            self.conn.execute(
                "UPDATE users SET suspended_at = %s WHERE user_id = %s",
                (now, user["user_id"]),
            )
            self.conn.commit()
            return None

        last_pw_change = user["last_password_change_at"]
        must_change = bool(user["must_change_password"])
        if last_pw_change is None:
            last_pw_change = now
        elif (now - last_pw_change) > timedelta(days=PASSWORD_MAX_AGE_DAYS):
            must_change = True

        self.conn.execute(
            """
            UPDATE users
            SET failed_attempts = 0, locked_until = NULL, last_login_at = %s,
                last_password_change_at = %s, must_change_password = %s
            WHERE user_id = %s
            """,
            (now, last_pw_change, must_change, user["user_id"]),
        )
        self.conn.commit()

        user["must_change_password"] = must_change

        token = create_access_token(user["user_id"])
        user_info = _build_user_info(self.conn, user)

        return LoginResponse(
            access_token=token,
            user=user_info,
        )

    def handle_failed_login(self, login: str) -> None:
        from app.services.user_service import UserService
        service = UserService(self.conn)
        service.handle_failed_login(login)

    def get_current_user(self, user_id: int) -> UserInfo | None:
        user = self.conn.execute(
            """
            SELECT u.*, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.user_id = %s
            """,
            (user_id,),
        ).fetchone()
        if not user:
            return None
        if not user["is_active"]:
            return None
        return _build_user_info(self.conn, user)

    def activate_account(self, user_id: int, code: str) -> UserInfo:
        from app.core.license_utils import validate_license
        from app.services.audit_service import log_action

        info = validate_license(code.strip())
        if info is None:
            raise ValueError("Code de sérialisation invalide.")

        user = self.conn.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        if user is None:
            raise ValueError("Utilisateur introuvable.")

        expected_code = (user.get("user_code") or "").strip().lower()
        embedded_code = (info.client_code or "").strip().lower()
        if expected_code and embedded_code != expected_code:
            raise ValueError(
                "Ce code de sérialisation ne correspond pas à votre compte client."
            )

        first_activation = not bool(user["is_activated"])
        now = datetime.now(timezone.utc)
        if first_activation:
            self.conn.execute(
                """
                UPDATE users
                SET sites_limit = %s, posts_limit = %s, is_activated = TRUE,
                    activation_code = %s, activated_at = %s, updated_at = %s
                WHERE user_id = %s
                """,
                (info.sites, info.posts, code.strip().upper(), now, now, user_id),
            )
            log_action(
                self.conn,
                user_id,
                "account_activation",
                "user",
                user_id,
                f"Activation du compte {user['login']} — sites: {info.sites}, postes: {info.posts}",
            )
        else:
            self.conn.execute(
                """
                UPDATE users
                SET sites_limit = %s, posts_limit = %s,
                    activation_code = %s, updated_at = %s
                WHERE user_id = %s
                """,
                (info.sites, info.posts, code.strip().upper(), now, user_id),
            )
            log_action(
                self.conn,
                user_id,
                "license_update",
                "user",
                user_id,
                f"Modification des limites (code de sérialisation) — sites: {info.sites}, postes: {info.posts}",
            )
        self.conn.commit()

        user = self.conn.execute(
            """
            SELECT u.*, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.user_id = %s
            """,
            (user_id,),
        ).fetchone()
        return _build_user_info(self.conn, user)

    # --- Activation par compte et liaison à un appareil (migration 016) ---

    def _get_license_posts(self, client_id: int) -> int:
        """Quota de postes du client (`clients.license_posts`).

        Depuis la migration 019, tout compte est rattaché à un client
        (users.client_id NOT NULL) : aucun repli sur un quota global.
        """
        row = self.conn.execute(
            "SELECT license_posts FROM clients WHERE id = %s",
            (client_id,),
        ).fetchone()
        if not row:
            raise ValueError("Ce compte n'est rattaché à aucun client.")
        return int(row["license_posts"] or 0)

    def _count_activated_accounts(self, client_id: int) -> int:
        """Comptes activés du client (même rattachement client, hors Super Admin)."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM users
            WHERE client_id = %s
              AND requires_activation = FALSE
              AND COALESCE(is_superadmin, FALSE) = FALSE
            """,
            (client_id,),
        ).fetchone()
        return row["cnt"] or 0

    def ensure_account_code(self, user_row: dict) -> str:
        """Garantit qu'un compte (ancien ou nouveau) possède un account_code.

        Rétrocompatibilité : les comptes créés avant la migration 016 n'ont pas
        d'account_code ; on en génère un à la volée puis on le stocke.
        """
        account_code = user_row.get("account_code")
        if account_code:
            return account_code
        from app.core.license_utils import generate_account_code
        account_code = generate_account_code()
        self.conn.execute(
            "UPDATE users SET account_code = %s WHERE user_id = %s",
            (account_code, user_row["user_id"]),
        )
        return account_code

    def bind_device(self, user_id: int, device_id: str) -> None:
        self.conn.execute(
            """
            UPDATE users
            SET authorized_device_id = %s, updated_at = %s
            WHERE user_id = %s
            """,
            (device_id, datetime.now(timezone.utc), user_id),
        )
        self.conn.commit()

    def activate_device_account(self, login: str, activation_code: str, device_id: str) -> dict:
        """Active un compte avec un code d'activation et le lie à un appareil.

        - Si le compte attend une activation (requires_activation), l'activation
          consomme un slot de licence postes (si le quota n'est pas déjà atteint).
        - Si le compte est déjà activé (changement / reliaison d'appareil),
          l'activation est gratuite (ne consomme pas de slot).
        """
        from app.core.license_utils import (
            fp6_from_string,
            verify_activation_code,
        )
        from app.services.audit_service import log_action

        if not device_id or not device_id.strip():
            raise ValueError("L'identifiant de l'appareil (X-Device-Id) est obligatoire.")

        user = self.conn.execute(
            """
            SELECT u.*, p.name AS profile_name
            FROM users u
            LEFT JOIN profiles p ON p.profile_id = u.profile_id
            WHERE u.login = %s
            """,
            (login,),
        ).fetchone()
        if not user:
            raise ValueError("Utilisateur introuvable.")
        if user.get("is_superadmin"):
            raise ValueError("Le compte admin suprême n'a pas besoin d'être activé.")

        account_code = self.ensure_account_code(user)

        fp6 = fp6_from_string(account_code)
        info = verify_activation_code(activation_code, fp6)
        if info is None:
            raise ValueError("Code d'activation invalide.")
        if not info.valid:
            raise ValueError("Ce code d'activation ne correspond pas au compte.")
        if info.expires_at < datetime.now(timezone.utc):
            raise ValueError("Ce code d'activation a expiré.")

        first_activation = bool(user.get("requires_activation"))
        if first_activation:
            client_id = user.get("client_id")
            if not client_id:
                raise ValueError("Ce compte n'est rattaché à aucun client : activation impossible.")
            quota = self._get_license_posts(client_id)
            used = self._count_activated_accounts(client_id)
            if used >= quota:
                raise ValueError(
                    f"Quota de postes atteint ({used}/{quota}). "
                    "Contactez le fournisseur pour augmenter votre licence."
                )

        now = datetime.now(timezone.utc)
        self.conn.execute(
            """
            UPDATE users
            SET requires_activation = FALSE, authorized_device_id = %s,
                activated_at = COALESCE(activated_at, %s), updated_at = %s
            WHERE user_id = %s
            """,
            (device_id, now, now, user["user_id"]),
        )
        action = "account_activation" if first_activation else "device_relink"
        description = (
            f"Activation du compte {login} et liaison à l'appareil {device_id}"
            if first_activation
            else f"Reliaison du compte {login} à l'appareil {device_id}"
        )
        log_action(self.conn, user["user_id"], action, "user", user["user_id"], description)
        self.conn.commit()

        return {
            "success": True,
            "user_id": user["user_id"],
            "login": login,
            "account_code": account_code,
            "first_activation": first_activation,
            "message": (
                "Compte activé et appareil lié." if first_activation
                else "Appareil relié au compte."
            ),
        }