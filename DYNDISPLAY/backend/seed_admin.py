"""Seed an initial admin user into the database."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.core.security import hash_password, verify_password
from app.db.database import get_connection


def seed():
    with get_connection() as conn:
        try:
            # Create admin profile if it doesn't exist
            admin_profile = conn.execute(
                "SELECT * FROM profiles WHERE name = 'Administrateur'"
            ).fetchone()
            if not admin_profile:
                admin_profile = conn.execute(
                    """
                    INSERT INTO profiles (name, description, is_active)
                    VALUES ('Administrateur', 'Profil administrateur avec tous les droits', TRUE)
                    RETURNING profile_id
                    """
                ).fetchone()
                print(f"Created profile: Administrateur (id={admin_profile['profile_id']})")
            else:
                print(f"Profile Administrateur already exists (id={admin_profile['profile_id']})")

            # Create regular user profile if it doesn't exist
            user_profile = conn.execute(
                "SELECT * FROM profiles WHERE name = 'Utilisateur'"
            ).fetchone()
            if not user_profile:
                user_profile = conn.execute(
                    """
                    INSERT INTO profiles (name, description, is_active)
                    VALUES ('Utilisateur', 'Profil utilisateur standard', TRUE)
                    RETURNING profile_id
                    """
                ).fetchone()
                print(f"Created profile: Utilisateur (id={user_profile['profile_id']})")
            else:
                print(f"Profile Utilisateur already exists (id={user_profile['profile_id']})")

            # Create supervisor profile if it doesn't exist (consultation only)
            supervisor_profile = conn.execute(
                "SELECT * FROM profiles WHERE name = 'Superviseur'"
            ).fetchone()
            if not supervisor_profile:
                supervisor_profile = conn.execute(
                    """
                    INSERT INTO profiles (name, description, is_active)
                    VALUES ('Superviseur', 'Profil de supervision (consultation uniquement)', TRUE)
                    RETURNING profile_id
                    """
                ).fetchone()
                print(f"Created profile: Superviseur (id={supervisor_profile['profile_id']})")
            else:
                print(f"Profile Superviseur already exists (id={supervisor_profile['profile_id']})")

            # Create admin user if it doesn't exist
            admin_user = conn.execute(
                "SELECT * FROM users WHERE login = 'admin'"
            ).fetchone()
            if not admin_user:
                admin_user = conn.execute(
                    """
                    INSERT INTO users (profile_id, login, password_hash, is_active, must_change_password)
                    VALUES (%s, 'admin', %s, TRUE, FALSE)
                    RETURNING user_id
                    """,
                    (admin_profile["profile_id"], hash_password("admin123")),
                ).fetchone()
                print(f"Created admin user: admin (id={admin_user['user_id']})")
                print("  password: admin123")
            else:
                print(f"Admin user already exists (id={admin_user['user_id']})")

            conn.commit()
            print("\nSeed completed successfully.")
        except Exception as e:
            conn.rollback()
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    seed()