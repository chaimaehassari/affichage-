"""Verifie que 000_baseline.sql + migrations 003..025 == schema de la base vivante.

Comparaison SEMANTIQUE (via le catalogue pg), pas textuelle : l'ordre des
elements d'un tableau de contrainte ou le formatage d'un defaut ne doivent pas
compter comme une difference.
"""

import os
import subprocess
import sys

PSQL = r"C:\Program Files\PostgreSQL\17\bin\psql.exe"
HOST, PORT, USER, PWD = "localhost", "5433", "postgres", "chaimae"
ENV = {**os.environ, "PGPASSWORD": PWD}
REF, REBUILT = "DYNDISPLAY", "DYNDISPLAY_BASELINE_VERIFY"

COLUMNS = """
SELECT table_name||'.'||column_name||' | '||data_type||coalesce('('||character_maximum_length||')','')
       ||coalesce('('||numeric_precision||','||numeric_scale||')','')
       ||' | null='||is_nullable||' | def='||coalesce(column_default,'-')
FROM information_schema.columns WHERE table_schema='public'
ORDER BY 1"""

TABLES = """
SELECT table_name||' | '||table_type FROM information_schema.tables
WHERE table_schema='public' ORDER BY 1"""

# Normalisation : retire le schema implicite et les casts de type, pour que
# 'public.x' et 'x', ou 'text' et 'text::text', ne comptent pas comme different.
INDEXES = """
SELECT indexname||' | '||regexp_replace(indexdef,'^CREATE (UNIQUE )?INDEX \\S+ ON \\S+\\.','')
FROM pg_indexes WHERE schemaname='public' ORDER BY 1"""

CONSTRAINTS = """
SELECT c.conname||' | '||c.contype::text||' | '||regexp_replace(
         pg_get_constraintdef(c.oid),'public\\.','','g')
FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
WHERE n.nspname='public' ORDER BY 1"""

SEQUENCES = """
SELECT c.relname||' | '||s.seqtypid::regtype::text
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_sequence s ON s.seqrelid=c.oid
WHERE c.relkind='S' AND n.nspname='public' ORDER BY 1"""

FK_DEFERRED = """
SELECT 'deferrable='||count(*) FILTER (WHERE condeferrable)
     ||' initdeferred='||count(*) FILTER (WHERE condeferred)
FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
WHERE n.nspname='public' AND c.contype='f'"""

QUERIES = [("TABLES", TABLES), ("COLUMNS", COLUMNS), ("INDEXES", INDEXES),
           ("CONSTRAINTS", CONSTRAINTS), ("SEQUENCES", SEQUENCES), ("FK_FLAGS", FK_DEFERRED)]

# `schema_migrations` est cree par scripts/migrate.py, pas par le schema de
# base : exclu des deux cotes pour que la comparaison porte sur le DDL metier.
RUNNER_OWNED = "schema_migrations"

_CAST = __import__("re").compile(r"::[a-z_ ]+(?:\[\])?")


def _semantic(entry):
    """Neutralise les purement formatiels : casts de type, parenthesees
    d'ANY, schema implicite. `ANY (ARRAY['A'::text])` et `ANY ((ARRAY['A'])::text[])`
    sont la meme contrainte : les distinguer serait un faux positif."""
    out = _CAST.sub("", entry)
    out = out.replace("(ARRAY[", "ARRAY[").replace("]::text[])", "])")
    out = out.replace("(", "").replace(")", "").replace(" ", "")
    return out


def owned_by_runner(entry):
    head = entry.split(" | ", 1)[0]
    return head.split(".", 1)[0] == RUNNER_OWNED or head == RUNNER_OWNED + "_pkey"


def psql(db, sql, tuples=True):
    fmt = ["-A", "-t"] if tuples else ["-q"]
    r = subprocess.run([PSQL, "-h", HOST, "-p", PORT, "-U", USER, "-d", db,
                        "-v", "ON_ERROR_STOP=1", *fmt, "-F", chr(31), "-c", sql],
                       capture_output=True, text=True, env=ENV)
    if r.returncode:
        raise RuntimeError(f"psql({db}) a echoue:\n{r.stderr}")
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}


def psql_run(db, sql_file):
    r = subprocess.run([PSQL, "-h", HOST, "-p", PORT, "-U", USER, "-d", db,
                        "-v", "ON_ERROR_STOP=1", "-q", "-f", sql_file],
                       capture_output=True, text=True, env=ENV)
    return r.returncode == 0, r.stdout + r.stderr


def main():
    baseline = sys.argv[1]
    mig_dir = sys.argv[2]

    subprocess.run([PSQL, "-h", HOST, "-p", PORT, "-U", USER, "-d", "postgres",
                    "-c", f'DROP DATABASE IF EXISTS "{REBUILT}"'],
                   capture_output=True, env=ENV)
    r = subprocess.run([PSQL, "-h", HOST, "-p", PORT, "-U", USER, "-d", "postgres",
                        "-c", f'CREATE DATABASE "{REBUILT}"'],
                       capture_output=True, text=True, env=ENV)
    if r.returncode:
        print("CREATE DATABASE:", r.stderr)
        return 1
    print(f"1. base '{REBUILT}' creee")

    ok, out = psql_run(REBUILT, baseline)
    if not ok:
        print("ECHEC application du baseline:\n", out)
        return 1
    print("2. baseline applique")

    import glob
    migs = sorted(glob.glob(f"{mig_dir}/*.sql"))
    for m in migs:
        if os.path.basename(m).startswith("000_"):
            continue
        ok, out = psql_run(REBUILT, m)
        if not ok:
            print(f"ECHEC migration {os.path.basename(m)}:\n{out}")
            return 1
    print(f"3. {len([m for m in migs if not os.path.basename(m).startswith('000_')])} migrations appliquees")

    print("\n=== COMPARAISON SEMANTIQUE ===")
    total_diff = 0
    for name, sql in QUERIES:
        a = {e for e in psql(REF, sql) if not owned_by_runner(e)}
        b = {e for e in psql(REBUILT, sql) if not owned_by_runner(e)}
        # Les objets propres a la migration 025 (table `licenses`) sont un
        # ECART ATTENDU : la base de developpement ne l'a pas encore recue.
        expect_025 = "--ignore-025" in sys.argv
        if expect_025:
            a = {e for e in a if not e.split(" | ", 1)[0].split(".", 1)[0].startswith("licenses")
                 and not e.split(" | ", 1)[0].startswith("idx_licenses")}
            b = {e for e in b if not e.split(" | ", 1)[0].split(".", 1)[0].startswith("licenses")
                 and not e.split(" | ", 1)[0].startswith("idx_licenses")}
        a = {_semantic(e) for e in a}
        b = {_semantic(e) for e in b}
        only_ref = sorted(a - b)
        only_new = sorted(b - a)
        if not only_ref and not only_new:
            print(f"  [OK]   {name:12} {len(a)} element(s) identiques")
        else:
            total_diff += len(only_ref) + len(only_new)
            print(f"  [DIFF] {name:12} ref={len(a)} reconstruit={len(b)}")
            for x in only_ref:
                print(f"          - manquant  : {x}")
            for x in only_new:
                print(f"          + en trop  : {x}")
    print("\nRESULTAT:", "IDENTIQUE" if total_diff == 0 else f"{total_diff} DIFFERENCE(S)")
    return 0 if total_diff == 0 else 2


if __name__ == "__main__":
    sys.exit(main())