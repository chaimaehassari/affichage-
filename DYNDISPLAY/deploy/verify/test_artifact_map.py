#!/usr/bin/env python
"""Verifie que le catalogue ARTIFACTS de scripts/migrate.py est trustworthy.

BUG DEFENDU ICI
---------------
Le runner "adopte" une migration comme deja appliquee des que son artefact
(schema) est present. Si l'artefact d'une migration N existe deja *avant* que N
ne soit jouee, la migration N est ADOPTEE puis SAUTEE sur une installation
neuve : ses colonnes/index/contraintes ne sont jamais crees.

Deux fenetres de faux positifs, toutes deux reelles dans ce depot :
  * artefact herite du schema de base 000
        007 -> uq_group_post      (contrainte UNIQUE equivalente dans 000)
        011 -> users.user_code    (colonne presente dans 000, ajoutee par
                                   aucune migration ; 011 ajoute sites_limit /
                                   posts_limit / is_activated /
                                   activation_code / activated_at)
  * artefact ajoute par une migration ANTERIEURE (piege de dependance)
        017 -> users.requires_activation (ajoutee par 016 ; 017 ajoute admin_id)
        019 -> users.client_id           (ajoutee par 018 ; 019 la rend NOT
                                   NULL et supprime clients.admin_id)

Le test rejoue donc la decision du runner migration par migration, dans
l'ordre, sur une base neuve : a chaque etape il sonde l'artefact, et note soit
"adoptee", soit "a jouer". Toute adoption autre que "000" est un echec.

Usage:
    python test_artifact_map.py
    DATABASE_URL=postgresql://user:pass@host:5432/base python test_artifact_map.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import migrate  # noqa: E402

# Versions volontairement SANS artefact : le runner doit les rejouer a chaque
# apply (toutes leurs instructions sont `IF NOT EXISTS` / `ON CONFLICT DO
# NOTHING`). Si l'une d'elles se met un jour a avoir une entree ARTIFACTS, le
# test echoue : soit l'artefact est wrongly capte (migration sautee sans
# effet), soit il disparait du contrat documente.
EXPECTED_WITHOUT_ARTIFACT = {"007", "024"}


def _admin_dsn() -> str:
    """DSN de maintenance : on se connecte a la base `postgres` pour en creer une."""
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        from app.core.config import get_settings

        dsn = str(get_settings().DATABASE_URL)
    parts = urlsplit(dsn)
    if not parts.scheme.startswith("postgres"):
        raise SystemExit(f"DSN non PostgreSQL: {dsn!r}")
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, ""))


def _dsn_for(dbname: str) -> str:
    parts = urlsplit(_admin_dsn())
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, ""))


def _drop_db(name: str) -> None:
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def main() -> int:
    dbname = f"dyndisplay_artifactmap_{uuid.uuid4().hex[:8]}"

    print(f"[*] base jetable : {dbname}")
    try:
        _drop_db(dbname)
        with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{dbname}"')

        with psycopg.connect(_dsn_for(dbname), row_factory=dict_row) as conn:
            migrations = migrate.list_migrations()
            print(f"[*] simulation du runner sur {len(migrations)} migrations (base neuve)\n")

            adopted_wrongly: list[str] = []
            contract: list[str] = []
            applied: list[str] = []

            for version, name, path in migrations:
                if migrate.artifact_present(conn, version):
                    verdict = "ADOPTE (pas joue)"
                    if version != "000":
                        adopted_wrongly.append(f"{version} ({name})")
                else:
                    verdict = "a jouer"
                    if version != "000":
                        applied.append(version)
                    print(f"  {version} {name:<42} {verdict:<20} <- application")
                    conn.execute(path.read_text(encoding="utf-8-sig"))

            print()
            for version, name, _path in migrations:
                spec = migrate.ARTIFACTS.get(version)
                status = "ADOPTE A TORT" if version in [a.split()[0] for a in adopted_wrongly] else "ok"
                if version in EXPECTED_WITHOUT_ARTIFACT and spec is not None:
                    status = "INATTENDU"
                    contract.append(f"{version} a une entree ARTIFACTS ({spec}) alors qu'elle doit etre rejouee")
                print(f"  {version} {name:<42} {status:<14} artefact={spec}")

            expected = [v for v, _n, _p in migrations if v != "000"]
            print()
            problems = adopted_wrongly + contract
            if problems:
                print("[ECHEC] contrat ARTIFACTS non respecte sur une base neuve :")
                for f in problems:
                    print(f"  - {f}")
                print(f"\n  {len(applied)}/{len(expected)} migrations jouees au lieu de {len(expected)}.")
                return 1

            print(f"[OK] les {len(expected)} migrations 003..025 sont toutes reellement jouees")
            print("     sur une base neuve (aucune adoption erronee).")
            print(f"[OK] {sorted(EXPECTED_WITHOUT_ARTIFACT)} correctement rejouees (sans artefact).")
            return 0
    finally:
        print(f"[*] suppression de {dbname}")
        try:
            _drop_db(dbname)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] nettoyage impossible : {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
