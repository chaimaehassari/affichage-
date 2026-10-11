#!/usr/bin/env python
"""Runner / audit des migrations DYNDISPLAY (PostgreSQL).

Usage:
    python scripts/migrate.py status --db DYNDISPLAY_TEST
    python scripts/migrate.py apply --version 009 --db DYNDISPLAY_TEST
    python scripts/migrate.py apply --db DYNDISPLAY_TEST
    python scripts/migrate.py apply --yes-i-know        # contourne le garde-fou

Garde-fou de cible :
  Chaque invocation affiche l'hote, le port et la BASE reellement visee. Par
  defaut l'operation est REFUSEE : il faut confirmer explicitement la cible
  avec ``--db <nom>`` (qui doit correspondre exactement a la base resolue) ou,
  en connaissance de cause, ``--yes-i-know``. Ce garde-fou existe parce qu'un
  ``apply`` sans confirmation a deja cible la mauvaise base (DEV) : la
  resolution de la cible (DATABASE_URL sinon POSTGRES_*) peut differer de ce
  que croit l'operateur.

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


def _load_deploy_env() -> None:
    """Charge le .env du dossier de DEPLOIEMENT s'il n'est pas dans le CWD.

    Dans le dossier livre, le .env est a la racine (a cote de install.bat) et
    les scripts sont appeles depuis backend/ : pydantic-settings, qui lit
    ".env" relatively au repertoire courant, ne le verrait pas et leverait
    "JWT_SECRET_KEY n'est pas defini" alors que tout est configure.

    On cherche donc, dans l'ordre :
      1. ./.env                    (dev : CWD = backend/, comportement actuel)
      2. <dossier du projet>/.env (deploiement : racine du dossier)
    Sans ecraser une variable deja definie : l'environnement du service reste
    prioritaire. Sans effet si aucun .env n'est trouve.
    """
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            try:
                from dotenv import load_dotenv

                load_dotenv(candidate, override=False)
            except ImportError:
                pass  # pip install requirements.txt apporte python-dotenv
            return


_load_deploy_env()

from app.core.config import build_postgres_dsn, get_settings  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

MIGRATIONS_DIR = BACKEND_DIR / "migrations"
FILE_RE = re.compile(r"^(\d{3})_.*\.sql$")

# Catalogue de vérification d'artefact par version : permet de reconnaître une
# migration déjà appliquée à la main (bases historiques) sans table de suivi.
# ("table", <nom>) | ("column", <table>, <colonne>) | ("index", <nom>)
# | ("setting", <clé>) | ("notnull", <table>, <colonne>)
#
# RÈGLE : l'artefact doit être une conséquence EXCLUSIVE de la migration.
# S'il existe déjà dans 000_baseline.sql, ou s'il est ajouté par une migration
# antérieure, le runner adopte la version et la saute — en installation neuve
# ses changements ne seraient jamais créés. Le test
# `deploy/verify/test_artifact_map.py` rejoue cette logique et échoue si une
# migration est adoptée à tort. Pièges corrigés dans ce dépôt :
#   007 uq_group_post          -> contrainte UNIQUE équivalente déjà dans 000
#   011 users.user_code        -> colonne déjà dans 000 (011 ajoute
#                                 sites_limit/post_limit/is_activated/
#                                 activation_code/activated_at)
#   017 users.requires_activation -> ajoutée par 016 (017 ajoute admin_id)
#   019 users.client_id        -> ajoutée par 018 (019 la rend NOT NULL)
#
# 000 : le schéma de base. Sur une base historique la table `users` existe déjà
# (elle a toujours été créée à la main avant qu'une migration ne la décrive) :
# sans cette entrée, le runner tenterait de rejouer 000 — inoffensif car le
# fichier est idempotent, mais inutile et trompeur dans `status`.
#
# 007 et 024 : aucune entrée, volontairement.
#   007 crée uq_group_post, uq_post_configuration, idx_group_posts_post et
#        idx_group_posts_group — les QUATRE existent déjà dans 000_baseline.sql
#        (contraintes UNIQUE équivalentes). Aucun artefact ne lui est propre :
#        son entrée capterait une migration sans effet. Elle est donc rejouée
#        à chaque apply, ce qui est sans risque (`IF NOT EXISTS` partout).
#   024 : backfill pur de données (admin_clients), sans artefact structurel
#        songeable. Idem : `ON CONFLICT DO NOTHING` + `NOT EXISTS`.
#
# Ces deux versions sont donc attendues comme « sans artefact » par
# `deploy/verify/test_artifact_map.py`, qui échoue si l'une d'elles se met un
# jour à adopter, ou si une autre migration est adoptée à tort.
ARTIFACTS = {
    "000": ("table", "users"),
    "003": ("column", "media", "page_count"),
    "004": ("column", "sync_jobs", "scheduled_at"),
    "005": ("column", "zone_media", "duration_seconds"),
    "006": ("setting", "code_client"),
    "008": ("table", "media_sync_state"),
    "009": ("column", "sync_jobs", "sync_profile_id"),
    "010": ("column", "users", "email"),
    "011": ("column", "users", "activation_code"),
    "012": ("column", "sites", "client_code"),
    "013": ("column", "media", "client_code"),
    "014": ("table", "user_group_access"),
    "015": ("column", "users", "is_superadmin"),
    "016": ("column", "users", "account_code"),
    "017": ("column", "users", "admin_id"),
    "018": ("table", "clients"),
    "019": ("notnull", "users", "client_id"),
    "020": ("column", "posts", "current_media_id"),
    "021": ("column", "posts", "reboot_enabled"),
    "022": ("column", "posts", "reboot_once_at"),
    "023": ("column", "media", "owner_user_id"),
    "025": ("table", "licenses"),
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
    # Colonne presente MAIS rendue obligatoire : c'est le seul artefact fiable
    # pour 019, dont la colonne users.client_id est ajoutee par 018 et que 019
    # rend NOT NULL. Sonder la colonne seule adopterait 019 a tort.
    "notnull": """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
              AND column_name = %s AND is_nullable = 'NO'
        ) AS ok
    """,
}

# Relation(s) que chaque sonde doit pouvoir lire. Sur une base VIERGE, avant
# d'avoir applique 000, la table sondee n'existe pas encore : PostgreSQL
# verifiant la totalite du statement AVANT execution, un garde `to_regclass`
# dans la meme requete ne suffit pas (UndefinedTable). La table est donc
# verifiee d'abord, separement, et la sonde n'est lancee que si elle existe.
REQUIRED_RELATION = {
    "table": lambda spec: (f"public.{spec[1]}",),
    "column": lambda spec: (f"public.{spec[1]}",),
    "index": lambda spec: (),
    "setting": lambda spec: ("public.general_settings",),
    "notnull": lambda spec: (f"public.{spec[1]}",),
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
    # La sonde ne peut pas tourner si la relation qu'elle interroge n'existe
    # pas encore (base vierge) : on la saute, ce qui vaut « artefact absent ».
    for relation in REQUIRED_RELATION[kind](spec):
        if conn.execute("SELECT to_regclass(%s) AS ok", (relation,)).fetchone()["ok"] is None:
            return False
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
    # utf-8-sig et non utf-8 : un BOM en tete de fichier se retrouve dans la
    # chaine envoyee a PostgreSQL et provoque
    #   SyntaxError: erreur de syntaxe sur ou près de « \ufeff »
    # Un editeur ou un outil de packaging peut introduire ce BOM ; mieux vaut
    # le tolerer que bloquer une installation.
    sql = path.read_text(encoding="utf-8-sig")
    if dry_run:
        return "séché (dry-run)"
    try:
        conn.execute(sql)
        # Une migration peut laisser la session dans un etat etrange : un dump
        # pg_dump, par exemple, emet `set_config('search_path','',false)`, qui
        # vide le search_path pour toute la session. L'INSERT ci-dessous etant
        # en non qualifie, il echouerait ensuite sur « schema_migrations n'existe
        # pas ». On remet un search_path sain apres CHAQUE migration, sans
        # dependre du contenu des fichiers.
        conn.execute("SELECT pg_catalog.set_config('search_path', 'public', false)")
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

def cmd_apply(conn, migrations, only: str | None, dry_run: bool, assume_yes: bool) -> int:
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
    if not dry_run and not assume_yes:
        # L'installateur et la mise a jour sont non interactifs : ils passent
        # par --yes. Sans lui, on garde la confirmation explicite, qui evite
        # d'ecrire en base sur un simple `apply` maladroit.
        try:
            confirm = input("Appliquer ? [y/N] ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("y", "yes"):
            print("Annulé.")
            return 1
    for version, name, path in pending:
        result = apply_migration(conn, version, name, path, dry_run)
        print(f"  {version}  {name}  -> {result}")
    return 0


def target_info(dsn: str) -> dict:
    """Hote / port / base / utilisateur reellement vises par ``dsn``.

    Analyse la chaine de connexion (peu importe la forme : URL ``postgresql://``
    ou paires ``host=... dbname=...``) pour que le garde-fou affiche la cible
    REELLE, pas celle que l'operateur croit utiliser.
    """
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(dsn)
    return {
        "host": info.get("host") or "localhost",
        "port": str(info.get("port") or 5432),
        "dbname": info.get("dbname") or "?",
        "user": info.get("user") or "?",
    }


def resolve_dsn() -> str:
    """DSN cible, meme resolution que l'application (DATABASE_URL sinon POSTGRES_*)."""
    settings = get_settings()
    if settings.DATABASE_URL:
        return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    return build_postgres_dsn(settings)


def check_target_confirmation(args, info: dict) -> int | None:
    """Garde-fou : refuse tant que la base cible n'est pas confirmee.

    Renvoie un code de sortie (3/4) si l'operation doit etre refusee, sinon None.
    ``--db <nom>`` doit correspondre EXACTEMENT (insensible a la casse) au nom de
    la base resolue ; ``--yes-i-know`` accepte explicitement n'importe quelle
    cible. Aucun des deux : refus par defaut.
    """
    dbname = info["dbname"]
    if getattr(args, "yes_i_know", False):
        return None
    requested = getattr(args, "db", None)
    if requested is not None:
        if requested.strip().casefold() == dbname.strip().casefold():
            return None
        print("", file=sys.stderr)
        print(f"  [REFUS] base demandee '{requested}' != base cible '{dbname}'.",
              file=sys.stderr)
        print("          Verifiez DATABASE_URL / POSTGRES_DB avant de continuer.",
              file=sys.stderr)
        print("", file=sys.stderr)
        return 4
    print("", file=sys.stderr)
    print("  [REFUS] operation refusee sans confirmation explicite de la base cible.",
          file=sys.stderr)
    print(f"          base cible : {dbname}  (hote {info['host']}:{info['port']})",
          file=sys.stderr)
    print("          Relancez avec :  --db " + dbname, file=sys.stderr)
    print("          (doit correspondre exactement) ou --yes-i-know en connaissance de cause.",
          file=sys.stderr)
    print("", file=sys.stderr)
    return 3


def _add_target_args(parser) -> None:
    parser.add_argument(
        "--db", metavar="NOM",
        help="confirme la base cible ; doit correspondre a la base resolue",
    )
    parser.add_argument(
        "--yes-i-know", action="store_true", dest="yes_i_know",
        help="accepte explicitement la base cible sans la nommer (risque assume)",
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="migrate.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_status = sub.add_parser("status", help="état des migrations")
    _add_target_args(p_status)
    p_apply = sub.add_parser("apply", help="applique les migrations en attente")
    p_apply.add_argument("--version", help="n'appliquer que cette version")
    p_apply.add_argument("--dry-run", action="store_true", help="simulation")
    p_apply.add_argument(
        "--yes", action="store_true",
        help="applique sans confirmation (installateur / mise a jour non interactifs)",
    )
    args = parser.parse_args()

    # CIBLE : DATABASE_URL si elle est renseignee, sinon POSTGRES_*.
    # Sans cet alignement, un .env qui ne definit QUE DATABASE_URL (forme
    # recommandee dans .env.example) faisait migrer une AUTRE base que celle
    # que sert l'application : POSTGRES_* restant sur ses valeurs par defaut
    # (localhost:5432/DYNDISPLAY_DEV). Meme resolution que app.db.database,
    # pour que migrations et application visent toujours la meme base.
    cible = resolve_dsn()
    info = target_info(cible)

    # Garde-fou : on affiche la cible REELLE et on refuse toute operation tant
    # qu'elle n'est pas confirmee (--db exact) ou assume explicitement
    # (--yes-i-know). C'est la protection contre l'incident "apply sur la
    # mauvaise base" : la resolution ci-dessus peut diverger de l'intention.
    print(f"  Cible PostgreSQL : {info['user']}@{info['host']}:{info['port']}/{info['dbname']}")
    refused = check_target_confirmation(args, info)
    if refused is not None:
        return refused

    try:
        conn = psycopg.connect(cible, row_factory=dict_row, connect_timeout=10)
    except psycopg.OperationalError as exc:
        # Message exploitable : un traceback psycopg sur une base injoignable
        # ne dit pas a l'installateur quoi corriger.
        _cible = cible.split("@")[-1] if "@" in cible else cible
        print("", file=sys.stderr)
        print("  [ERREUR] Connexion PostgreSQL impossible.", file=sys.stderr)
        print(f"            Cible : {_cible}", file=sys.stderr)
        print(f"            {str(exc).strip().splitlines()[0]}", file=sys.stderr)
        print("", file=sys.stderr)
        print("            Verifiez :", file=sys.stderr)
        print("              - le service PostgreSQL est-il demarre ?", file=sys.stderr)
        print("              - POSTGRES_HOST / POSTGRES_PORT (ou DATABASE_URL)",
              file=sys.stderr)
        print("                correspondent-ils a la configuration reelle ?",
              file=sys.stderr)
        print("              - le role et la base existent-ils ?", file=sys.stderr)
        print("              - le pare-feu bloque-t-il le port ?", file=sys.stderr)
        print("", file=sys.stderr)
        print("            Diagnostic detaille :", file=sys.stderr)
        print("              python scripts/check_db.py", file=sys.stderr)
        return 2
    try:
        # Verrou consultatif : deux `apply` simultanes (installation et mise a
        # jour qui se croisent, ou deux administrateurs) appliqueraient sinon
        # les memes migrations en double. 730001 est arbitraire mais fixe.
        conn.execute("SELECT pg_advisory_lock(730001)")
        try:
            migrations = list_migrations()
            if args.command == "status":
                return cmd_status(conn, migrations)
            if args.command == "apply":
                return cmd_apply(conn, migrations, args.version, args.dry_run, args.yes)
            return 1
        finally:
            # Le deverrouillage doit aboutir meme si le corps a leve : une
            # transaction en erreur refuse toute commande, Unlock compris.
            # rollback() remet d'abord la session dans un etat executable.
            try:
                conn.rollback()
                conn.execute("SELECT pg_advisory_unlock(730001)")
            except Exception:
                pass
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())