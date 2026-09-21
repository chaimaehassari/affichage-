"""Traitement des jobs de sync orphelins (rapport d'audit 2026-09-18).

Stratégie (même logique que SyncService.recover_orphan_jobs) : les jobs jamais
pris en charge par un worker (PENDING depuis > 30 min, ou SCHEDULED dont
l'échéance est dépassée de > 30 min) sont marqués FAILED avec un message
explicite, plutôt que relancés automatiquement (pas de boucle de relance ni de
re-upload compétitif ; relance par décision humaine ou via la synchro auto du
jour suivant).

Sur la base locale au 20/09/2026, le scheduler (déjà rechargé avec le
correctif) a traité 256 jobs orphelins. Ce script :
  1. snapshote l'état courant de ces jobs dans une table de référence
     (_snapshot_sync_orphans_20260920) — avec leur statut d'origine reconstruit
     depuis le message (PENDING ou SCHEDULED) ;
  2. traite tous les orphelins restants par la même méthode que le scheduler
     (idempotent : rien à faire si déjà traité) ;
  3. écrit un script d'annulation (undo.sql) restaurant les jobs à leur état
     d'origine (statut PENDING/SCHEDULED, error_message NULL, completed_at NULL).

Usage (depuis backend/, car le .env est lu relatif au répertoire courant) :
  python scripts/recover_orphan_jobs.py            # exécution réelle
  python scripts/recover_orphan_jobs.py --dry-run  # ne fait que diagnostiquer
"""

import argparse
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend")

from app.core.config import get_settings  # noqa: E402
from app.services.sync_service import ORPHAN_JOB_TIMEOUT, SyncService  # noqa: E402

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

SNAPSHOT_TABLE = "_snapshot_sync_orphans_20260920"
TREATED_MARKER = "Job orphelin"


def build_conn():
    s = get_settings()
    return psycopg.connect(
        host=s.POSTGRES_HOST,
        port=int(s.POSTGRES_PORT or 5432),
        dbname=s.POSTGRES_DB,
        user=s.POSTGRES_USER,
        password=s.POSTGRES_PASSWORD,
        row_factory=dict_row,
    )


def original_status_from_message(msg: str | None) -> str:
    if not msg:
        return "PENDING"
    m = re.search(r"statut\s+(\w+)", msg)
    return m.group(1) if m else "PENDING"


def snapshot_jobs(conn, rows):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
                sync_job_id bigint PRIMARY KEY,
                post_id bigint,
                original_status text,
                status text,
                started_at timestamptz,
                completed_at timestamptz,
                error_message text,
                created_at timestamptz,
                scheduled_at timestamptz,
                sync_profile_id integer,
                snapshotted_at timestamptz DEFAULT now()
            )
            """
        )
        for r in rows:
            cur.execute(
                f"""
                INSERT INTO {SNAPSHOT_TABLE}
                    (sync_job_id, post_id, original_status, status, started_at,
                     completed_at, error_message, created_at, scheduled_at,
                     sync_profile_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (sync_job_id) DO UPDATE SET
                    original_status = EXCLUDED.original_status,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    r["sync_job_id"], r["post_id"],
                    original_status_from_message(r["error_message"]),
                    r["status"], r["started_at"], r["completed_at"],
                    r["error_message"], r["created_at"], r["scheduled_at"],
                    r["sync_profile_id"],
                ),
            )
    conn.commit()


def build_undo(conn, out_path: str) -> int:
    rows = conn.execute(
        f"SELECT sync_job_id, original_status FROM {SNAPSHOT_TABLE} ORDER BY sync_job_id"
    ).fetchall()
    lines = [
        "-- Annulation : restaure les jobs orphelins traités à leur état d'origine.",
        "-- Tables de référence : %s" % SNAPSHOT_TABLE,
        ""
    ]
    for r in rows:
        lines.append(
            f"UPDATE sync_jobs SET status = '{r['original_status']}', "
            f"error_message = NULL, completed_at = NULL, started_at = NULL "
            f"WHERE sync_job_id = {r['sync_job_id']};"
        )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="diagnostique sans modifier la base")
    args = ap.parse_args()

    conn = build_conn()
    svc = SyncService(conn)

    # 1. Orphelins déjà traités (message de la reprise) et orphelins restants.
    already = conn.execute(
        """
        SELECT j.sync_job_id, j.post_id, j.status, j.started_at, j.completed_at,
               j.error_message, j.created_at, j.scheduled_at, j.sync_profile_id
        FROM sync_jobs j
        WHERE j.status = 'FAILED' AND j.error_message LIKE %s
        """,
        (TREATED_MARKER + "%",),
    ).fetchall()
    remaining = svc.find_orphan_jobs()

    print(f"Orphelins déjà traités par la reprise : {len(already)}")
    print(f"Orphelins restants (find_orphan_jobs) : {len(remaining)}")

    if args.dry_run:
        conn.rollback()
        conn.close()
        print("DRY-RUN : aucune modification.")
        return

    # 2. Traitement des restants (même méthode que le scheduler).
    treated = list(already)
    if remaining:
        recovered = svc.recover_orphan_jobs()
        print(f"Orphelins restants marqués FAILED : {recovered}")
        treated = list(already) + [
            {
                "sync_job_id": j["sync_job_id"], "post_id": j["post_id"],
                "status": "FAILED",
                "started_at": None, "completed_at": datetime.now(timezone.utc),
                "error_message": (
                    f"Job orphelin : jamais pris en charge par un worker dans le délai de "
                    f"{int(ORPHAN_JOB_TIMEOUT.total_seconds() // 60)} min (statut {j['status']})."
                ),
                "created_at": j["created_at"], "scheduled_at": j["scheduled_at"],
                "sync_profile_id": None,
            }
            for j in remaining
        ]
    # Dédupliquer (un job ne peut pas être dans les deux listes).
    seen = set()
    treated_uniq = []
    for t in treated:
        if t["sync_job_id"] in seen:
            continue
        seen.add(t["sync_job_id"])
        treated_uniq.append(t)

    # 3. Snapshot de référence (état traité + statut d'origine reconstruit).
    snapshot_jobs(conn, treated_uniq)
    print(f"Snapshot : {len(treated_uniq)} jobs enregistrés dans {SNAPSHOT_TABLE}")

    # 4. Script d'annulation.
    undo_path = r"C:\Users\hp\AppData\Local\Temp\opencode\undo_recover_sync_orphans_20260920.sql"
    n = build_undo(conn, undo_path)
    print(f"Undo écrit : {undo_path} ({n} instructions)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()