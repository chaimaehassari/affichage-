#!/usr/bin/env python
"""Runner / audit des migrations DYNDISPLAY (PostgreSQL).

Usage:
    python scripts/migrate.py status           # état de chaque migration (audit)
    python scripts/migrate.py apply            # applique les migrations en attente
    python scripts/migrate.py apply --version 009
    python scripts/migrate.py apply --dry-run  # simule sans rien écrire

Concepts :
  * Les migrations sont les fichiers 0NN_*.sql du dossier ``migrations``.
  * Un suivi est tenu dans la table ``schema_migrations`` (créée ici-même si
    absente) pour garantir l'idempotence.
  * Sur une base historique (migrations appliquées à la main sans suivi), la
    commande ``status``/``apply`` "adopte" d'abord les versions dont l'artefact
    existe déjà (via un catalogue de vérifications), puis n'applique que les
    versions réellement en attente.
"""
import argparse
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

MIGRATIONS_DIR = BACKEND_DIR / "migrations"
FILE_RE = re.compile(r"^(\d{3})_.*\.sql$")

# Catalogue de vérification d'artefact par version : permet de reconnaître une
# migration déjà appliquée à la main (bases historiques) sans table de suivi.
# ("table", <nom>) | ("column", <table>, <colonne>) | ("index", <nom>) | ("setting", <clé>)
ARTIFACTS = {
    "003": ("column", "media", "page_count"),
    "004": ("column", "sync_jobs", "scheduled_at"),
    "005": ("column", "zone_media", "duration_seconds"),
    "006": ("setting", "code_client"),
    "007": ("index", "uq_group_post"),
    "008": ("table", "media_sync_state"),
    "009": ("column", "sync_jobs", "sync_profile_id"),
    "010": ("column", "users", "email"),
    "011": ("column", "users", "user_code"),
    "012": ("column", "sites", "client_code"),
    "013": ("column", "media", "client_code"),
    "014": ("table", "user_group_access"),
    "015": ("column", "users", "is_superadmin"),
    "016": ("column", "users", "account_code"),
    "017": ("column", "users", "requires_activation"),
    "018": ("table", "clients"),
    "019": ("column", "users", "client_id"),
}

CHECK_SQL = {
    "table": "SELECT to_regclass(%s) IS NOT NULL AS ok",
    "column": """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        ) AS ok
    """,
    "index": "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = %s) AS ok",
    "setting": "SELECT EXISTS (SELECT 1 FROM general_settings WHERE setting_key = %s) AS ok",
}


def list_migrations() -> list[tuple[str, str, Path]]:
    items = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = FILE_RE.match(path.name)
        if m:
            items.append((m.group(1), path.name, path))
    return items


def artifact_present(conn, version: str) -> bool:
    spec = ARTIFACTS.get(version)
    if not spec:
        return False
    kind = spec[0]
    params = spec[1:] if kind != "table" else (f"public.{spec[1]}",)
    row = conn.execute(CHECK_SQL[kind], params).fetchone()
    return bool(row["ok"])


def ensure_tracking_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def tracked_versions(conn) -> set[str]:
    rows = conn.execute("SELECT version, name FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def seed_from_artifacts(conn, migrations) -> None:
    """Adopte les versions déjà appliquées à la main (artefact présent)."""
    tracked = tracked_versions(conn)
    inserted = 0
    for version, name, _path in migrations:
        if version in tracked:
            continue
        if artifact_present(conn, version):
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (version, name),
            )
            inserted += 1
    if inserted:
        conn.commit()
        print(f"[adoption] {inserted} version(s) déjà appliquée(s) enregistrée(s).")


def cmd_status(conn, migrations) -> int:
    ensure_tracking_table(conn)
    seed_from_artifacts(conn, migrations)
    tracked = tracked_versions(conn)
    print(f"{'ver':<5}{'fichier':<40}{'artefact':<9}{'suivi':<9}")
    print("-" * 63)
    for version, name, _ in migrations:
        artifact = "OK" if artifact_present(conn, version) else "MISSING"
        tracked_str = "oui" if version in tracked else "non"
        marker = "" if artifact == "OK" or version in tracked else "<- en attente"
        print(f"{version:<5}{name:<40}{artifact:<9}{tracked_str:<9}{marker}")
    return 0


def apply_migration(conn, version, name, path, dry_run: bool) -> str:
    sql = path.read_text(encoding="utf-8")
    if dry_run:
        return "séché (dry-run)"
    try:
        conn.execute(sql)
        conn.execute(
            """
            INSERT INTO schema_migrations (version, name) VALUES (%s, %s)
            ON CONFLICT (version) DO UPDATE SET name = EXCLUDED.name
            """,
            (version, name),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return "appliquée"

def cmd_apply(conn, migrations, only: str | None, dry_run: bool) -> int:
    ensure_tracking_table(conn)
    seed_from_artifacts(conn, migrations)
    tracked = tracked_versions(conn)
    pending = []
    for version, name, path in migrations:
        if only and version != only:
            continue
        if version in tracked:
            continue
        pending.append((version, name, path))
    if not pending:
        print("Aucune migration en attente.")
        return 0
    print("Migrations à appliquer :")
    for version, name, _ in pending:
        print(f"  {version}  {name}")
    if not dry_run:
        confirm = input("Appliquer ? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Annulé.")
            return 1
    for version, name, path in pending:
        result = apply_migration(conn, version, name, path, dry_run)
        print(f"  {version}  {name}  -> {result}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="migrate.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_status = sub.add_parser("status", help="état des migrations")
    p_apply = sub.add_parser("apply", help="applique les migrations en attente")
    p_apply.add_argument("--version", help="n'appliquer que cette version")
    p_apply.add_argument("--dry-run", action="store_true", help="simulation")
    args = parser.parse_args()

    settings = get_settings()
    conn = psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=int(settings.POSTGRES_PORT or 5432),
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        row_factory=dict_row,
    )
    try:
        migrations = list_migrations()
        if args.command == "status":
            return cmd_status(conn, migrations)
        if args.command == "apply":
            return cmd_apply(conn, migrations, args.version, args.dry_run)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())