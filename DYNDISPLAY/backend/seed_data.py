"""Seed V2 test data for demonstration."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.core.security import hash_password
from app.db.database import get_connection

TEST_USERS = [
    {
        "user_code": "U001",
        "login": "admin",
        "password": "admin123",
        "profile_name": "Administrateur",
        "is_active": True,
        "zones": [1, 2, 3, 4, 5, 6, 7, 8],
        "all_permissions": True,
    },
    {
        "user_code": "U002",
        "login": "supervisor1",
        "password": "Sup@1234",
        "profile_name": "Superviseur",
        "is_active": True,
        "zones": [1, 2, 3, 4],
        "menu_perms": ["menu_conception", "menu_sync", "menu_media"],
        "user_perms": {"user_list": True},
        "site_perms": {"list_sites_posts": True},
    },
    {
        "user_code": "U003",
        "login": "operator1",
        "password": "Oper@1234",
        "profile_name": "Utilisateur",
        "is_active": True,
        "zones": [1, 2, 3],
        "menu_perms": ["menu_media"],
        "user_perms": {},
        "site_perms": {},
    },
    {
        "user_code": "U004",
        "login": "operator2",
        "password": "Oper@1234",
        "profile_name": "Utilisateur",
        "is_active": True,
        "zones": [5, 6],
        "menu_perms": ["menu_conception", "menu_config"],
        "user_perms": {},
        "site_perms": {"list_sites_posts": True, "create_site": True},
    },
    {
        "user_code": "U005",
        "login": "viewer1",
        "password": "View@1234",
        "profile_name": "Superviseur",
        "is_active": True,
        "zones": [1, 2],
        "menu_perms": ["menu_media"],
        "user_perms": {},
        "site_perms": {"list_sites_posts": True},
    },
    {
        "user_code": "U006",
        "login": "inactive1",
        "password": "Inact@123",
        "profile_name": "Utilisateur",
        "is_active": False,
        "zones": [1],
        "menu_perms": [],
        "user_perms": {},
        "site_perms": {},
    },
]


def seed():
    with get_connection() as conn:
        try:
            profiles = {p["name"]: p for p in conn.execute("SELECT * FROM profiles").fetchall()}
            permissions = {p["code"]: p for p in conn.execute("SELECT * FROM permissions").fetchall()}

            for data in TEST_USERS:
                existing = conn.execute(
                    "SELECT * FROM users WHERE login = %s",
                    (data["login"],),
                ).fetchone()
                if existing:
                    print(f"  User '{data['login']}' already exists (id={existing['user_id']}), skipping")
                    continue

                profile = profiles.get(data["profile_name"])
                if not profile:
                    print(f"  Profile '{data['profile_name']}' not found, skipping {data['login']}")
                    continue

                user = conn.execute(
                    """
                    INSERT INTO users (profile_id, user_code, login, password_hash, is_active, must_change_password)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING user_id
                    """,
                    (
                        profile["profile_id"],
                        data["user_code"],
                        data["login"],
                        hash_password(data["password"]),
                        data["is_active"],
                        True if data["login"] != "admin" else False,
                    ),
                ).fetchone()
                user_id = user["user_id"]
                print(f"  Created user: {data['login']} (id={user_id}, profile={data['profile_name']})")

                for zone in data["zones"]:
                    conn.execute(
                        "INSERT INTO user_zone_access (user_id, zone_number, is_allowed) VALUES (%s, %s, TRUE)",
                        (user_id, zone),
                    )

                if data.get("all_permissions"):
                    for perm in permissions.values():
                        conn.execute(
                            """
                            INSERT INTO user_permissions (user_id, permission_id, can_view, can_create, can_update, can_delete)
                            VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE)
                            """,
                            (user_id, perm["permission_id"]),
                        )
                else:
                    menu_perms = data.get("menu_perms", [])
                    user_perms = data.get("user_perms", {})
                    site_perms = data.get("site_perms", {})

                    for code in menu_perms:
                        if code in permissions:
                            conn.execute(
                                """
                                INSERT INTO user_permissions (user_id, permission_id, can_view, can_create, can_update, can_delete)
                                VALUES (%s, %s, TRUE, FALSE, FALSE, FALSE)
                                """,
                                (user_id, permissions[code]["permission_id"]),
                            )

                    for code, allowed in user_perms.items():
                        if allowed and code in permissions:
                            conn.execute(
                                """
                                INSERT INTO user_permissions (user_id, permission_id, can_view, can_create, can_update, can_delete)
                                VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE)
                                """,
                                (user_id, permissions[code]["permission_id"]),
                            )

                    for code, allowed in site_perms.items():
                        if allowed and code in permissions:
                            conn.execute(
                                """
                                INSERT INTO user_permissions (user_id, permission_id, can_view, can_create, can_update, can_delete)
                                VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE)
                                """,
                                (user_id, permissions[code]["permission_id"]),
                            )

            conn.commit()
            print("\nSeed completed.")

            users = conn.execute(
                """
                SELECT u.user_id, u.user_code, u.login, u.is_active, p.name AS profile_name
                FROM users u
                LEFT JOIN profiles p ON p.profile_id = u.profile_id
                ORDER BY u.user_id
                """
            ).fetchall()
            total = len(users)
            print(f"\nTotal users: {total}")

            for u in users:
                perms_count = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM user_permissions WHERE user_id = %s",
                    (u["user_id"],),
                ).fetchone()["cnt"]
                zones_count = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM user_zone_access WHERE user_id = %s",
                    (u["user_id"],),
                ).fetchone()["cnt"]
                print(
                    f"  {u['user_code']} | {u['login']:15s} | {(u['profile_name'] or ''):15s} | "
                    f"{'Actif' if u['is_active'] else 'Inactif':8s} | {perms_count} perms | {zones_count} zones"
                )

        except Exception as e:
            conn.rollback()
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    seed()