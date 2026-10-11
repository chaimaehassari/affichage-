"""Rend migrations/000_baseline.sql idempotent (IF NOT EXISTS / DO $$ ... IF).

Pourquoi : les migrations 008, 014, 015, 018 et 025 du projet creent leurs
objets avec `IF NOT EXISTS`. Le schema de base doit suivre la meme convention,
sinon une table `schema_migrations` perdue ou tronquee rendrait toute
re-execution impossible a recovering.

Transformation :
  CREATE TABLE public.x (      -> CREATE TABLE IF NOT EXISTS public.x (
  CREATE SEQUENCE public.x     -> CREATE SEQUENCE IF NOT EXISTS public.x
  CREATE INDEX ... ;           -> DO $$ ... IF NOT EXISTS (pg_class) ... $$;
  ALTER TABLE ONLY public.x
      ADD CONSTRAINT n ... ;   -> DO $$ ... IF NOT EXISTS (pg_constraint) ... $$;
"""

import re
import sys

TABLE = re.compile(r"^CREATE TABLE (public\.\w+) \($")
SEQUENCE = re.compile(r"^CREATE SEQUENCE (public\.\w+)$")
INDEX = re.compile(r"^CREATE (UNIQUE )?INDEX (\w+) ON (public\.\w+)")
ALTER = re.compile(r"^ALTER TABLE ONLY (public\.\w+)$")
ADDCONSTRAINT = re.compile(r"^\s+ADD CONSTRAINT (\w+) ")

IDX_GUARD = """DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = '{name}') THEN
        {stmt}
    END IF;
END $$;"""

CON_GUARD = """DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = '{relname}'
                     AND con.conname = '{name}') THEN
        ALTER TABLE ONLY {table} ADD CONSTRAINT {name} {rest};
    END IF;
END $$;"""


def transform(lines):
    out, stats = [], {"table": 0, "seq": 0, "idx": 0, "con": 0}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")

        m = TABLE.match(stripped)
        if m:
            out.append(f"CREATE TABLE IF NOT EXISTS {m.group(1)} (")
            stats["table"] += 1
            i += 1
            continue

        m = SEQUENCE.match(stripped)
        if m:
            out.append(f"CREATE SEQUENCE IF NOT EXISTS {m.group(1)}")
            stats["seq"] += 1
            i += 1
            continue

        m = INDEX.match(stripped)
        if m:
            # Le ';' de fin de ligne est RETIRE de la ligne d'origine mais
            # REPOSE dans le garde : chaque instruction d'un bloc DO $$ a
            # besoin de son propre terminateur.
            stmt = stripped.rstrip().rstrip(";") + ";"
            out.append(IDX_GUARD.format(name=m.group(2), stmt=stmt))
            stats["idx"] += 1
            i += 1
            continue

        # ALTER TABLE ONLY ... suivi de ADD CONSTRAINT ... sur la ligne d'apres.
        m_alt, m_con = ALTER.match(stripped), None
        if m_alt and i + 1 < len(lines):
            m_con = ADDCONSTRAINT.match(lines[i + 1])
        if m_alt and m_con:
            table, name = m_alt.group(1), m_con.group(1)
            # pg_class.relname ne porte PAS le schema : comparer avec
            # 'public.zone_media' ne trouverait jamais rien et le garde
            # laisserait toujours passer la creation.
            relname = table.split(".", 1)[-1]
            rest = lines[i + 1].strip()
            rest = re.sub(r"^ADD CONSTRAINT \w+ ", "", rest).rstrip(";")
            out.append(CON_GUARD.format(table=table, relname=relname, name=name, rest=rest))
            stats["con"] += 1
            i += 2
            continue

        out.append(line)
        i += 1
    return out, stats


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        original = fh.read().splitlines(keepends=True)

    result, stats = transform(original)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(result)

    print(f"{path} rendu idempotent :")
    for key, label in [("table", "CREATE TABLE IF NOT EXISTS"),
                       ("seq", "CREATE SEQUENCE IF NOT EXISTS"),
                       ("idx", "CREATE INDEX guards"),
                       ("con", "ADD CONSTRAINT guards")]:
        print(f"  {stats[key]:3d}  {label}")


if __name__ == "__main__":
    main()