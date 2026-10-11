#!/usr/bin/env python
"""Consolidation des médias dupliqués INTRA-client (Phase 2, Partie 3, Option B).

Le stockage média historisait un fichier physique par upload. L'Option B
adopte un stockage adressé par contenu DANS UN MÊME CLIENT : un seul fichier
par `(client_code, checksum)`, plusieurs lignes `media` pouvant le référencer.

Ce script traite les données existantes. Il est IDEMPOTENT : une fois les
groupes consolidés, une seconde exécution ne trouve plus rien.

Usage (depuis backend/) :
    python scripts/migrate_media_dedup.py                 # dry-run (défaut)
    python scripts/migrate_media_dedup.py --apply         # écrit réellement

La base cible vient de `--database-url`, sinon de `TEST_DATABASE_URL` puis
`DATABASE_URL`. Par sécurité, un nom de base ne contenant pas `_test` est
refusé sauf `--allow-non-test`.

Rollback : restaurer le dump DB + la copie du dossier médias pris AVANT
l'exécution (voir rapport Phase 2).
"""
import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.services.media_maintenance import consolidate, find_duplicate_groups  # noqa: E402
from app.services.media_storage import get_media_store  # noqa: E402


def _resolve_url(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _db_name(url: str) -> str:
    tail = url.rsplit("/", 1)[-1]
    return tail.split("?", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None,
                        help="URL Postgres (défaut: TEST_DATABASE_URL puis DATABASE_URL)")
    parser.add_argument("--apply", action="store_true",
                        help="exécute réellement la consolidation (défaut: dry-run)")
    parser.add_argument("--allow-non-test", action="store_true",
                        help="autorise une base dont le nom ne contient pas '_test'")
    args = parser.parse_args()

    url = _resolve_url(args.database_url)
    if not url:
        print("ERREUR : aucune URL (ni --database-url, ni TEST_DATABASE_URL, ni DATABASE_URL).")
        return 2

    name = _db_name(url)
    if "_test" not in name.lower() and not args.allow_non_test:
        print(f"ERREUR : la base '{name}' ne contient pas '_test'. "
              f"Utiliser --allow-non-test pour forcer.")
        return 2

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== migrate_media_dedup [{mode}] base={name} ===")

    conn = psycopg.connect(url, row_factory=dict_row)
    try:
        groups = find_duplicate_groups(conn)
        print(f"Groupes (client_code, checksum) avec plusieurs fichiers : {len(groups)}")
        for group in groups:
            print(f"  client={group['client_code']!r} checksum={group['checksum']} "
                  f"lignes={group['row_count']} fichiers={list(group['paths'])}")

        if not args.apply:
            print("\nDry-run : aucune écriture. Relancer avec --apply pour consolider.")
            return 0

        if not groups:
            print("\nRien à consolider (idempotent).")
            return 0

        with get_media_store() as store:
            stats = consolidate(conn, store, apply=True)
        print(f"\nLignes repointées : {stats['rows_repointed']}")
        print(f"Fichiers supprimés: {stats['files_removed']}")

        remaining = find_duplicate_groups(conn)
        print(f"Vérification idempotence : {len(remaining)} groupe(s) restant(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
