"""Seed V2 permissions and profiles."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.db.database import get_connection


PERMISSIONS = [
    # Gestion des utilisateurs
    ("user_list", "Liste des utilisateurs", "Consulter la liste des utilisateurs"),
    ("user_create", "Création utilisateur", "Créer un nouvel utilisateur"),
    ("user_update", "Modification utilisateur", "Modifier un utilisateur existant"),
    ("user_delete", "Suppression utilisateur", "Supprimer un utilisateur"),
    # Gestion des sites/postes
    ("list_sites_posts", "Liste des sites/postes", "Consulter la liste des sites et postes"),
    ("create_site", "Création site", "Créer un site"),
    ("update_site", "Modification site", "Modifier un site"),
    ("delete_site", "Suppression site", "Supprimer un site"),
    ("create_post", "Création poste", "Créer un poste"),
    ("update_post", "Modification poste", "Modifier un poste"),
    ("delete_post", "Suppression poste", "Supprimer un poste"),
    # Menus application
    ("menu_conception", "Conception", "Accès au menu Conception"),
    ("menu_sync", "Synchronisation", "Accès au menu Synchronisation"),
    ("menu_media", "Médiathèque", "Accès au menu Médiathèque"),
    ("menu_config", "Configuration", "Accès au menu Configuration"),
]


def seed():
    with get_connection() as conn:
        created = 0
        for code, name, description in PERMISSIONS:
            existing = conn.execute(
                "SELECT permission_id FROM permissions WHERE code = %s",
                (code,),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO permissions (code, name, description, is_active) VALUES (%s, %s, %s, TRUE)",
                    (code, name, description),
                )
                created += 1
        conn.commit()
        print(f"Seeded {created} new permissions ({len(PERMISSIONS)} total defined)")

        profiles = conn.execute("SELECT profile_id, name FROM profiles ORDER BY profile_id").fetchall()
        print(f"\nProfiles: {[(p['profile_id'], p['name']) for p in profiles]}")

        perms = conn.execute("SELECT code, name FROM permissions ORDER BY permission_id").fetchall()
        print(f"Permissions: {[(p['code'], p['name']) for p in perms]}")


if __name__ == "__main__":
    seed()