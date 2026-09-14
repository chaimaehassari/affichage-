"""Migrate permissions: replace site_list/create/update/delete with proper site+post permissions."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.database import get_connection

OLD_CODES = ["site_list", "site_create", "site_update", "site_delete"]

NEW_PERMISSIONS = [
    ("list_sites_posts", "Liste des sites/postes", "Consulter la liste des sites et postes"),
    ("create_site", "Création site", "Créer un site"),
    ("update_site", "Modification site", "Modifier un site"),
    ("delete_site", "Suppression site", "Supprimer un site"),
    ("create_post", "Création poste", "Créer un poste"),
    ("update_post", "Modification poste", "Modifier un poste"),
    ("delete_post", "Suppression poste", "Supprimer un poste"),
]

def migrate():
    with get_connection() as conn:
        # Delete old user_permission rows for old codes
        old_perms = conn.execute(
            "SELECT permission_id FROM permissions WHERE code = ANY(%s)",
            (OLD_CODES,),
        ).fetchall()
        old_ids = [p["permission_id"] for p in old_perms]
        if old_ids:
            cur = conn.execute(
                "DELETE FROM user_permissions WHERE permission_id = ANY(%s)",
                (old_ids,),
            )
            print(f"Deleted {cur.rowcount} user_permission rows for old site permissions")
            cur2 = conn.execute(
                "DELETE FROM permissions WHERE code = ANY(%s)",
                (OLD_CODES,),
            )
            print(f"Deleted {cur2.rowcount} old permission rows")

        # Create new permissions
        created = 0
        for code, name, desc in NEW_PERMISSIONS:
            existing = conn.execute(
                "SELECT permission_id FROM permissions WHERE code = %s",
                (code,),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO permissions (code, name, description, is_active) VALUES (%s, %s, %s, TRUE)",
                    (code, name, desc),
                )
                created += 1
        conn.commit()
        print(f"Created {created} new permissions")

        # Show final state
        perms = conn.execute(
            "SELECT permission_id, code, name FROM permissions ORDER BY permission_id"
        ).fetchall()
        print(f"\nAll permissions ({len(perms)}):")
        for p in perms:
            print(f"  {p['permission_id']:2d} | {p['code']:25s} | {p['name']}")

if __name__ == "__main__":
    migrate()