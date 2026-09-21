#!/usr/bin/env python
"""Backfill réversible des postes touchés par le bug de synchro silencieux.

Bug : avant le correctif de sync_service.run_sync(), l'échec (avalé) de
l'INSERT dans media_sync_state laissait la transaction PostgreSQL en erreur.
Le commit final était donc perdu : le job partait en COMPLETED mais
``posts.last_sync_at`` ne s'écrivait jamais (le poste restait "never_synced"
dans la supervision), et ``posts.is_up_to_date`` n'était pas remis à TRUE.

Ce script reconstruit l'état que le code aurait dû écrire :
  * pour chaque poste ayant >= 1 job COMPLETED et last_sync_at NULL :
      last_sync_at = MAX(completed_at) des jobs COMPLETED,
      is_up_to_date  = TRUE

Réversibilité : l'état d'origine est sauvegardé dans la table
``_snapshot_posts_last_sync_20260920`` et un script d'annulation est écrit
sur disque (chemin affiché en fin d'exécution).

Usage :
    python scripts/backfill_posts_last_sync.py --dry-run
    python scripts/backfill_posts_last_sync.py
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
import psycopg  # noqa: E402

SNAPSHOT_TABLE = "_snapshot_posts_last_sync_20260920"
UNDO_DIR = Path(r"C:\Users\hp\AppData\Local\Temp\opencode")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="simuler sans écrire")
    args = parser.parse_args()

    settings = get_settings()
    conn = psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=int(settings.POSTGRES_PORT or 5432),
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )
    try:
        # 1. Sauvegarde réversible de l'état d'origine.
        conn.execute(f"DROP TABLE IF EXISTS {SNAPSHOT_TABLE}")
        conn.execute(
            f"""
            CREATE TABLE {SNAPSHOT_TABLE} AS
            SELECT p.post_id, p.last_sync_at, p.is_up_to_date
            FROM posts p
            WHERE p.last_sync_at IS NULL
              AND EXISTS (
                  SELECT 1 FROM sync_jobs j
                  WHERE j.post_id = p.post_id AND j.status = 'COMPLETED'
              )
            """
        )
        conn.commit()

        affected = conn.execute(f"SELECT COUNT(*) FROM {SNAPSHOT_TABLE}").fetchone()[0]
        total_null = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE last_sync_at IS NULL"
        ).fetchone()[0]
        print(f"Postes à corriger (last_sync_at NULL avec un job COMPLETED) : {affected}")
        print(f"Postes encore last_sync_at NULL (aucun job COMPLETED, legitimes) : {total_null - affected}")

        if args.dry_run or affected == 0:
            print("Mode dry-run : aucune écriture.")
            return 0

        # 2. Reconstruction.
        conn.execute(
            """
            UPDATE posts p
            SET last_sync_at = j.max_completed, is_up_to_date = TRUE
            FROM (
                SELECT j.post_id, MAX(j.completed_at) AS max_completed
                FROM sync_jobs j
                WHERE j.status = 'COMPLETED'
                GROUP BY j.post_id
            ) j
            WHERE p.post_id = j.post_id
              AND p.last_sync_at IS NULL
            """
        )
        conn.commit()

        # 3. Script d'annulation.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        undo_path = UNDO_DIR / f"undo_backfill_posts_last_sync_{stamp}.sql"
        undo_path.write_text(
            f"""-- Annulation du backfill postes.last_sync_at (rolled {stamp})
-- Restaure l'état d'origine depuis le snapshot puis supprime le snapshot.
BEGIN;
UPDATE posts p SET last_sync_at = s.last_sync_at, is_up_to_date = s.is_up_to_date
FROM {SNAPSHOT_TABLE} s WHERE p.post_id = s.post_id;
DROP TABLE {SNAPSHOT_TABLE};
COMMIT;
""",
            encoding="utf-8",
        )
        print(f"Backfill appliqué à {affected} poste(s).")
        print(f"Script d'annulation écrit : {undo_path}")

        after_ok = conn.execute(
            """
            SELECT COUNT(*) FROM posts p
            JOIN sync_jobs j ON j.post_id = p.post_id AND j.status = 'COMPLETED'
            WHERE p.is_up_to_date = TRUE
            """
        ).fetchone()[0]
        print(f"Postes avec COMPLETED désormais is_up_to_date = TRUE : {after_ok}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())