"""Seed an initial admin user into the database.

Le mot de passe du compte admin n'est JAMAIS en dur : il est lu depuis la
variable d'environnement SEED_ADMIN_PASSWORD (réservée au dev/tests) ou,
à défaut, généré aléatoirement et affiché UNE SEULE FOIS, à la création.
"""
import secrets
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.core.security import hash_password, verify_password
from app.db.database import get_connection


def _bootstrap_password() -> str:
    return os.environ.get("SEED_ADMIN_PASSWORD") or secrets.token_urlsafe(18)


def seed():
    password = _bootstrap_password()
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
                    INSERT INTO users (profile_id, login, password_hash, is_active, must_change_password, is_superadmin, requires_activation, client_id)
                    VALUES (%s, 'admin', %s, TRUE, FALSE, TRUE, FALSE, (SELECT id FROM clients ORDER BY id LIMIT 1))
                    RETURNING user_id
                    """,
                    (admin_profile["profile_id"], hash_password(password)),
                ).fetchone()
                print(f"Created admin user: admin (id={admin_user['user_id']})")
                print(f"  password: {password}  <-- à conserver EN UN SEUL exemplaire")
                print("  (ouverture de session : admin / mot de passe ci-dessus)")
            else:
                # S'assurer que le compte admin par défaut est le Super Admin
                conn.execute(
                    "UPDATE users SET is_superadmin = TRUE, requires_activation = FALSE WHERE user_id = %s",
                    (admin_user["user_id"],),
                )
                print(f"Admin user already exists (id={admin_user['user_id']}) ; mot de passe non modifié")

            conn.commit()
            print("\nSeed completed successfully.")
        except Exception as e:
            conn.rollback()
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    seed()