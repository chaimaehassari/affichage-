"""Transfere le contenu d'un client source vers un client cible.

Le script de backfill `backfill_content_client_code.py` corrige la FORME des
codes clients ; celui-ci deplace le contenu d'un client vers un autre, quand un
admin doitPosseder un contenu existant plutot que de le partager.

 precaution
 ----------
 operation destructive sur `sites.client_code`, `media.client_code` et
 `users.client_id`. Un snapshot `_snapshot_transfer_<date>` est ecrit avant
 toute modification, et un script SQL d'annulation est produit.

Usage :
    python scripts/transfer_client_content.py --source 3C48DBF1 --target AMINA01
    python scripts/transfer_client_content.py --source 3C48DBF1 --target AMINA01 --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

SNAPSHOT_TABLE = "_snapshot_transfer_20260930"


def _connect() -> psycopg.Connection:
    from app.core.config import get_settings

    settings = get_settings()
    return psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=int(settings.POSTGRES_PORT or 5432),
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        row_factory=dict_row,
    )


def _ensure_snapshot(conn: psycopg.Connection, source: str) -> None:
    """Copie les lignes touchees pour pouvoir annuler.

    Le snapshot est `CREATE TABLE IF NOT EXISTS` : il n'est donc ecrit qu'une
    fois. Relancer le script apres une premiere application ne doit pas
    ecraser les valeurs d'origine par les valeurs deja migrees.
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} AS
        SELECT s.site_id, s.client_code, 'site' AS kind
        FROM sites s WHERE s.client_code = %s
        """,
        (source,),
    )
    conn.execute(
        f"""
        INSERT INTO {SNAPSHOT_TABLE} (site_id, client_code, kind)
        SELECT m.media_id, m.client_code, 'media'
        FROM media m WHERE m.client_code = %s
          AND NOT EXISTS (
              SELECT 1 FROM {SNAPSHOT_TABLE} t
              WHERE t.site_id = m.media_id AND t.kind = 'media')
        """,
        (source,),
    )
    conn.execute(
        f"""
        INSERT INTO {SNAPSHOT_TABLE} (site_id, client_code, kind)
        SELECT u.user_id, c.code_client, 'user'
        FROM users u JOIN clients c ON c.id = u.client_id
        WHERE c.code_client = %s
          AND NOT EXISTS (
              SELECT 1 FROM {SNAPSHOT_TABLE} t
              WHERE t.site_id = u.user_id AND t.kind = 'user')
        """,
        (source,),
    )
    conn.commit()
    total = conn.execute(f"SELECT count(*) n FROM {SNAPSHOT_TABLE}").fetchone()["n"]
    print(f"Snapshot {SNAPSHOT_TABLE} : {total} lignes")


def _counts(conn: psycopg.Connection, code: str) -> dict:
    sites = conn.execute(
        "SELECT count(*) n FROM sites WHERE client_code = %s", (code,)
    ).fetchone()["n"]
    posts = conn.execute(
        """SELECT count(*) n FROM posts p
           JOIN sites s ON s.site_id = p.site_id WHERE s.client_code = %s""",
        (code,),
    ).fetchone()["n"]
    media = conn.execute(
        "SELECT count(*) n FROM media WHERE client_code = %s", (code,)
    ).fetchone()["n"]
    users = conn.execute(
        """SELECT count(*) n FROM users u JOIN clients c ON c.id = u.client_id
           WHERE c.code_client = %s""",
        (code,),
    ).fetchone()["n"]
    return {"sites": sites, "posts": posts, "media": media, "users": users}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="code client source")
    parser.add_argument("--target", required=True, help="code client cible")
    parser.add_argument("--target-name", default=None, help="nom du client cible")
    parser.add_argument("--apply", action="store_true", help="applique (sinon dry-run)")
    args = parser.parse_args()

    conn = _connect()
    try:
        source_client = conn.execute(
            "SELECT * FROM clients WHERE code_client = %s", (args.source,)
        ).fetchone()
        if not source_client:
            print(f"Client source introuvable : {args.source}")
            return 1

        target_client = conn.execute(
            "SELECT * FROM clients WHERE code_client = %s", (args.target,)
        ).fetchone()
        if not target_client:
            if not args.apply:
                print(f"[dry-run] Le client cible {args.target} n'existe pas : il sera cree.")
            else:
                conn.execute(
                    """INSERT INTO clients (code_client, nom_client, license_sites, license_posts)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (
                        args.target,
                        args.target_name or args.target,
                        source_client["license_sites"],
                        source_client["license_posts"],
                    ),
                )
                conn.commit()
                target_client = conn.execute(
                    "SELECT * FROM clients WHERE code_client = %s", (args.target,)
                ).fetchone()
                print(f"Client cible cree : {args.target} ({args.target_name or args.target})")

        before = _counts(conn, args.source)
        after_target = _counts(conn, args.target)
        target_name = (
            target_client["nom_client"] if target_client else (args.target_name or args.target)
        )
        print(f"\nSource {args.source} ({source_client['nom_client']}) : {before}")
        print(f"Cible {args.target} ({target_name}) : {after_target}")

        if not args.apply:
            print("\n[dry-run] Aucune modification. Relancez avec --apply.")
            _ensure_snapshot(conn, args.source)
            return 0

        _ensure_snapshot(conn, args.source)

        moved_sites = conn.execute(
            "UPDATE sites SET client_code = %s WHERE client_code = %s",
            (args.target, args.source),
        ).rowcount
        moved_media = conn.execute(
            "UPDATE media SET client_code = %s WHERE client_code = %s",
            (args.target, args.source),
        ).rowcount
        moved_users = conn.execute(
            """UPDATE users u SET client_id = %s
               FROM clients c
               WHERE c.code_client = %s AND u.client_id = c.id""",
            (target_client["id"], args.source),
        ).rowcount
        conn.commit()

        print(f"\nDeplace : {moved_sites} sites, {moved_media} medias, {moved_users} comptes")
        print(f"Source apres  : {_counts(conn, args.source)}")
        print(f"Cible apres   : {_counts(conn, args.target)}")
        print(
            f"\nAnnulation : psql -f annuler_transfer_20260930.sql\n"
            f"(restaure {before['sites'] + before['media'] + before['users']} lignes depuis {SNAPSHOT_TABLE})"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
