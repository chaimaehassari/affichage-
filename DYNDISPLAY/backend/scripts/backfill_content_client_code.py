#!/usr/bin/env python
"""Backfill reversible de l'attribution client du contenu (sites, media).

Bug : deux espaces de codes cohabitaient dans la colonne texte `client_code`.

- `clients.code_client` (ex. `3C48DBF1`) : le code du CLIENT. C'est lui que
  contient `admin_clients.client_code`, donc ce sur quoi filtre un Admin.
- `users.user_code` (ex. `SCO8B02F5`) : le code du COMPTE, saisi a la
  connexion a la place du mot de passe.

`client_scope()` renvoyait le `user_code` du compte client : un site ou un
media cree par un compte etait donc stocke sous le code du compte. Aucun
Admin ne pouvait le trouver (il filtre sur le code client), et le compte
lui-meme ne le reverait plus apres le passage du perimetre au code client.

Ce script reconstruit le code canonique attendu :

* `sites.client_code`   <- `clients.code_client` de `sites.client_id`
                          (la FK est correctement renseignee, meme quand
                          `client_code` est NULL ou faux) ;
* `media.client_code`   <- `clients.code_client` du client de l'auteur
                          (`media.owner_user_id` -> `users.client_id`).
                          `media` n'a pas de `client_id` : sans auteur
                          rattache, le code reste NULL (le media ne reste
                          visible que de son auteur, cf. `media_scope_sql`).

Sont corrigees les litterales `'{}'`, `'None'`, `'[]'` issues d'un ancien
ecriture de la liste Python du scope, ainsi que les codes de comptes.

Reversibilite : l'etat d'origine est sauvegarde dans
``_snapshot_content_client_code_20260930`` et un script d'annulation est
ecrit sur disque (chemin affiche en fin d'execution).

Usage :
    python scripts/backfill_content_client_code.py --dry-run
    python scripts/backfill_content_client_code.py
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
import psycopg  # noqa: E402

SNAPSHOT_TABLE = "_snapshot_content_client_code_20260930"
UNDO_DIR = Path(r"C:\Users\hp\AppData\Local\Temp\opencode")

# Un `client_code` qui ne correspond ni a un client, ni au `user_code` d'un
# compte rattache a un client : on le laisse tel quel plutot que de l'effacer.
_LITERAL_JUNK = ("{}", "None", "[]", "none", "")


def connect():
    settings = get_settings()
    return psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=int(settings.POSTGRES_PORT or 5432),
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )


def count(conn) -> None:
    sites_total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    sites_visibles = conn.execute(
        """
        SELECT COUNT(*) FROM sites s
        JOIN clients c ON c.id = s.client_id
        WHERE s.client_code = c.code_client
        """
    ).fetchone()[0]
    sites_a_corriger = conn.execute(
        """
        SELECT COUNT(*) FROM sites s
        JOIN clients c ON c.id = s.client_id
        WHERE s.client_code IS DISTINCT FROM c.code_client
        """
    ).fetchone()[0]
    media_total = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    media_visibles = conn.execute(
        """
        SELECT COUNT(*) FROM media m
        JOIN users u ON u.user_id = m.owner_user_id
        JOIN clients c ON c.id = u.client_id
        WHERE m.client_code = c.code_client
        """
    ).fetchone()[0]
    media_a_corriger = conn.execute(
        """
        SELECT COUNT(*) FROM media m
        JOIN users u ON u.user_id = m.owner_user_id
        JOIN clients c ON c.id = u.client_id
        WHERE m.client_code IS DISTINCT FROM c.code_client
        """
    ).fetchone()[0]
    media_litteral = conn.execute(
        "SELECT COUNT(*) FROM media WHERE client_code IN ('{}', 'None', '[]')"
    ).fetchone()[0]

    print(f"Sites  : {sites_total} au total, {sites_visibles} avec un client_code correct")
    print(f"Media  : {media_total} au total, {media_visibles} avec un client_code correct")
    print(f"Sites a corriger (client_id renseigne, code faux/NULL) : {sites_a_corriger}")
    print(f"Medias a corriger (auteur rattache a un client)        : {media_a_corriger}")
    print(f"Medias contenant une litterale '{{}}' / 'None'         : {media_litteral}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="simuler sans ecrire")
    args = parser.parse_args()

    conn = connect()
    try:
        print("=== Etat actuel ===")
        count(conn)

        if args.dry_run:
            print("\nMode dry-run : aucune ecriture.")
            return 0

        # 1. Sauvegarde reversible de l'etat d'origine.
        conn.execute(f"DROP TABLE IF EXISTS {SNAPSHOT_TABLE}")
        conn.execute(
            f"""
            CREATE TABLE {SNAPSHOT_TABLE} AS
            SELECT 'site'::text AS row_kind, s.site_id::bigint AS row_id,
                   s.client_code AS old_client_code
            FROM sites s LEFT JOIN clients c ON c.id = s.client_id
            WHERE s.client_code IS DISTINCT FROM c.code_client
            UNION ALL
            SELECT 'media'::text, m.media_id::bigint, m.client_code
            FROM media m
            JOIN users u ON u.user_id = m.owner_user_id
            JOIN clients c ON c.id = u.client_id
            WHERE m.client_code IS DISTINCT FROM c.code_client
            UNION ALL
            SELECT 'media_junk'::text, m.media_id::bigint, m.client_code
            FROM media m
            WHERE m.client_code IN ('{{}}', 'None', '[]')
            """
        )
        conn.commit()
        affected = conn.execute(f"SELECT COUNT(*) FROM {SNAPSHOT_TABLE}").fetchone()[0]
        print(f"\nLignes sauvegardees dans {SNAPSHOT_TABLE} : {affected}")
        if affected == 0:
            print("Rien a corriger.")
            return 0

        # 2. Reconstruction : sites via leur FK, medias via leur auteur.
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sites s
                SET client_code = c.code_client, updated_at = now()
                FROM clients c
                WHERE c.id = s.client_id
                  AND s.client_code IS DISTINCT FROM c.code_client
                """
            )
            sites_fixed = cur.rowcount
            cur.execute(
                """
                UPDATE media m
                SET client_code = c.code_client, updated_at = now()
                FROM users u
                JOIN clients c ON c.id = u.client_id
                WHERE u.user_id = m.owner_user_id
                  AND m.client_code IS DISTINCT FROM c.code_client
                """
            )
            media_fixed = cur.rowcount
            # Les litterales '{}' / 'None' d'un auteur non rattache : on les
            # vide plutot que de les laisser (elles ne designent aucun client
            # et faussent le dedoublonnage par checksum).
            cur.execute(
                """
                UPDATE media
                SET client_code = NULL, updated_at = now()
                WHERE client_code IN ('{}', 'None', '[]')
                """
            )
            junk_fixed = cur.rowcount
        conn.commit()
        print(f"Sites corriges  : {sites_fixed}")
        print(f"Medias corriges : {media_fixed}")
        print(f"Literales videes: {junk_fixed}")

        # 3. Script d'annulation.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        UNDO_DIR.mkdir(parents=True, exist_ok=True)
        undo_path = UNDO_DIR / f"undo_backfill_content_client_code_{stamp}.sql"
        undo_path.write_text(
            f"""-- Annulation du backfill content.client_code (rolled {stamp})
BEGIN;
UPDATE sites s SET client_code = k.old_client_code
FROM {SNAPSHOT_TABLE} k
WHERE k.row_kind = 'site' AND s.site_id = k.row_id;

UPDATE media m SET client_code = k.old_client_code
FROM {SNAPSHOT_TABLE} k
WHERE k.row_kind IN ('media', 'media_junk') AND m.media_id = k.row_id;

DROP TABLE {SNAPSHOT_TABLE};
COMMIT;
""",
            encoding="utf-8",
        )
        print(f"Script d'annulation ecrit : {undo_path}")

        print("\n=== Apres correction ===")
        count(conn)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
