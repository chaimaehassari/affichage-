from datetime import datetime, timedelta, timezone

from psycopg import Connection

from app.core.security import create_access_token, create_refresh_token, verify_password
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
        is_superadmin=bool(user_row.get("is_superadmin", False)),
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
        refresh = create_refresh_token(user["user_id"])
        user_info = _build_user_info(self.conn, user)

        return LoginResponse(
            access_token=token,
            refresh_token=refresh,
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
