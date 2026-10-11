"""Test du garde-fou de cible de migrate.py.

Verifie que migrate.py :
  * affiche la base reellement visee ;
  * REFUSE toute operation sans confirmation explicite (--db exact) ;
  * REFUSE quand --db ne correspond pas a la base resolue ;
  * accepte --db (insensible a la casse) et --yes-i-know ;
  * refuse AVANT toute ecriture (aucune connexion/creation de table).

Hermetique : cree puis supprime une base jetable ; ne touche a aucune base
existante.
"""

import os
import subprocess

PSQL = r"C:\Program Files\PostgreSQL\17\bin\psql.exe"
HOST, PORT, USER, PWD = "localhost", "5433", "postgres", "chaimae"
TMP = "dyndisplay_guard_test"
PY = r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend\.venv\Scripts\python.exe"
MIGRATE = r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend\scripts\migrate.py"
ENV = {**os.environ, "PGPASSWORD": PWD,
       "POSTGRES_HOST": HOST, "POSTGRES_PORT": PORT,
       "POSTGRES_DB": TMP, "POSTGRES_USER": USER, "POSTGRES_PASSWORD": PWD,
       "JWT_SECRET_KEY": "test", "SUPREME_ADMIN_SECRET": "test",
       "PYTHONPATH": r"C:\Users\hp\Desktop\all\DYNDISPLAY\backend"}

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
    r = subprocess.run([PY, MIGRATE, *args], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout + r.stderr


def main():
    raw(f'DROP DATABASE IF EXISTS "{TMP}"')
    _, err = raw(f'CREATE DATABASE "{TMP}"')
    if err:
        print(err)
        return 1

    print("=== 1. status sans drapeau : refus attendu ===")
    rc, out = migrate("status")
    check("refus (code 3)", rc == 3, f"rc={rc}")
    check("affiche la base cible", TMP in out)
    check("message [REFUS]", "[REFUS]" in out)

    print("\n=== 2. status --db different : refus attendu ===")
    rc, out = migrate("status", "--db", "UNE_AUTRE_BASE")
    check("refus (code 4)", rc == 4, f"rc={rc}")
    check("signale l'ecart", "UNE_AUTRE_BASE" in out and TMP in out)

    print("\n=== 3. apply sans drapeau : refus AVANT toute ecriture ===")
    rc, out = migrate("apply", "--yes")
    check("refus (code 3)", rc == 3, f"rc={rc}")
    got, _ = raw("SELECT to_regclass('public.schema_migrations')", TMP)
    check("aucune table creee (pas de connexion)", got in ("",), f"obtenu '{got}'")

    print("\n=== 4. status --db correct : accepte ===")
    rc, out = migrate("status", "--db", TMP)
    check("accepte (code 0)", rc == 0, f"rc={rc}")
    check("affiche la cible", f"/{TMP}" in out)

    print("\n=== 5. --db insensible a la casse : accepte ===")
    rc, out = migrate("status", "--db", TMP.lower())
    check("accepte (code 0)", rc == 0, f"rc={rc}")

    print("\n=== 6. --yes-i-know : accepte ===")
    rc, out = migrate("status", "--yes-i-know")
    check("accepte (code 0)", rc == 0, f"rc={rc}")

    raw(f'DROP DATABASE IF EXISTS "{TMP}"')

    print("\n" + "=" * 62)
    if failures:
        print(f"ECHEC : {len(failures)} test(s) en echec")
        for f in failures:
            print("  -", f)
        return 1
    print("TOUS LES TESTS PASSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
