"""Test de bout en bout du runner de migrations sur une base VIERGE.

Enchaine : creation d'une base vide -> migrate.py status -> apply --yes ->
comparaison semantique avec la base de developpement -> apply --yes une seconde
fois (idempotence) -> verification que les donnees survivent a une migration.
"""

import os
import subprocess
import sys

PSQL = r"C:\Program Files\PostgreSQL\17\bin\psql.exe"
HOST, PORT, USER, PWD = "localhost", "5433", "postgres", "chaimae"
REF, FRESH = "DYNDISPLAY", "dyndisplay_fresh_test"
PY = r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend\.venv\Scripts\python.exe"
MIGRATE = r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend\scripts\migrate.py"
ENV = {**os.environ, "PGPASSWORD": PWD,
       "POSTGRES_HOST": HOST, "POSTGRES_PORT": PORT,
       "POSTGRES_DB": FRESH, "POSTGRES_USER": USER, "POSTGRES_PASSWORD": PWD,
       "JWT_SECRET_KEY": "test", "SUPREME_ADMIN_SECRET": "test",
       "PYTHONPATH": r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend"}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_baseline import (psql as catalog_psql, psql_run,  # noqa: E402
                             _semantic, owned_by_runner, SEQUENCES)

failures = []


def check(label, ok, detail=""):
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def raw(sql, db="postgres"):
    r = subprocess.run([PSQL, "-h", HOST, "-p", PORT, "-U", USER, "-d", db, "-t", "-A",
                        "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True, env=ENV)
    return r.stdout.strip(), r.stderr


def migrate(*args):
    # `--db FRESH` : satisfait le garde-fou de cible de migrate.py (la base
    # reellement ciblee doit etre confirmee explicitement).
    r = subprocess.run([PY, MIGRATE, *args, "--db", FRESH], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout + r.stderr


def main():
    print("=== 1. base vierge ===")
    raw(f'DROP DATABASE IF EXISTS "{FRESH}"')
    _, err = raw(f'CREATE DATABASE "{FRESH}"')
    if err:
        print(err)
        return 1

    print("\n=== 2. status sur base vierge (ne doit pas planter) ===")
    rc, out = migrate("status")
    check("status ne plante pas", rc == 0)
    check("000 listee en attente", "000" in out and "en attente" in out)

    print("\n=== 3. apply --yes ===")
    rc, out = migrate("apply", "--yes")
    check("apply retourne 0", rc == 0, out.strip().splitlines()[-1] if out else "")
    applied = [l for l in out.splitlines() if "appliquée" in l]
    check("24 migrations appliquees", len(applied) == 24, f"{len(applied)}/24")

    print("\n=== 4. comparaison semantique avec la base de developpement ===")
    # La base de developpement n'a pas encore recu la 025 ; on l'exclut des
    # deux cotes comme dans verify_baseline.py --ignore-025.
    def snap(db):
        s = catalog_psql(db, "SELECT table_name||' | '||column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY 1")
        t = catalog_psql(db, "SELECT table_name||' | '||table_type FROM information_schema.tables WHERE table_schema='public' ORDER BY 1")
        q = catalog_psql(db, "SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY 1")
        s2 = catalog_psql(db, "SELECT c.relname||' | '||s.seqtypid::regtype::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_sequence s ON s.seqrelid=c.oid WHERE c.relkind='S' AND n.nspname='public' ORDER BY 1")
        def strip_025(items):
            return {_semantic(e) for e in items
                    if not e.split(" | ", 1)[0].split(".", 1)[0].startswith("licenses")
                    and not e.split(" | ", 1)[0].startswith("idx_licenses")}
        return strip_025(t), strip_025(s), strip_025(q), strip_025(s2)

    ref, new = snap(REF), snap(FRESH)
    names = ["tables", "colonnes", "index", "sequences"]
    for name, a, b in zip(names, ref, new):
        check(f"{name} identiques", a == b,
              "" if a == b else f"ref={len(a)} nouveau={len(b)} "
                               f"manque={sorted(a - b)[:3]} en_trop={sorted(b - a)[:3]}")

    print("\n=== 5. les 24 versions sont-elles tracees ? ===")
    got, _ = raw("SELECT count(*) FROM schema_migrations", FRESH)
    check("24 lignes dans schema_migrations", got == "24", f"obtenu {got}")
    got, _ = raw("SELECT string_agg(version, ',' ORDER BY version) FROM schema_migrations", FRESH)
    check("000 est tracee", "000" in got.split(","), got)

    print("\n=== 6. idempotence : second apply ===")
    rc, out = migrate("apply", "--yes")
    check("second apply retourne 0", rc == 0)
    check("aucune migration en attente", "Aucune migration en attente" in out)
    got, _ = raw("SELECT count(*) FROM schema_migrations", FRESH)
    check("toujours 24 lignes", got == "24", f"obtenu {got}")

    print("\n=== 7. les donnees survivent-elles a une migration ? ===")
    # On insere un client, on applique une migration bidon 026, on re-applique.
    raw("INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
        "VALUES ('TESTCLIENT', 'Client de test', 5, 10)", FRESH)
    mig_dir = os.path.join(os.path.dirname(MIGRATE), "..", "migrations")
    mig_dir = os.path.abspath(mig_dir)
    probe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_probe_026.sql")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("ALTER TABLE clients ADD COLUMN IF NOT EXISTS probe_marker TEXT;\n")
    shutil_copy(probe, os.path.join(mig_dir, "026_probe_noop.sql"))
    try:
        rc, out = migrate("apply", "--yes")
        check("migration 026 appliquee", rc == 0 and "026_probe_noop" in out)
        got, _ = raw("SELECT nom_client FROM clients WHERE code_client='TESTCLIENT'", FRESH)
        check("donnees preservees", got == "Client de test", f"obtenu '{got}'")
        rc, out = migrate("status")
        check("026 marquee appliquee", "026" in out)
    finally:
        os.remove(os.path.join(mig_dir, "026_probe_noop.sql"))
        if os.path.exists(probe):
            os.remove(probe)

    print("\n" + "=" * 62)
    if failures:
        print(f"ECHEC : {len(failures)} test(s) en echec")
        for f in failures:
            print("  -", f)
        return 1
    print("TOUS LES TESTS PASSENT")
    return 0


def shutil_copy(src, dst):
    with open(src, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())


if __name__ == "__main__":
    sys.exit(main())