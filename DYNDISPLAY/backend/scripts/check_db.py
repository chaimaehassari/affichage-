"""Diagnostic de la connexion PostgreSQL, executable AVANT toute migration.

Objectif : distinguer trois situations que l'installateur doit expliquer
différemment, avant de tenter le moindre changement en base.

  1. la configuration est-elle valide ?
  2. le serveur PostgreSQL est-il joignable ?
  3. la base cible existe-t-elle et l'authentification est-elle correcte ?

Sortie :
  0  tout est bon (la base existe, on peut migrer)
  1  probleme de configuration ou de connectivite (rien n'a ete modifie)
"""

import os
import sys
from pathlib import Path

# Permet d'executer le script depuis la racine du projet comme depuis scripts/ :
# le paquet `app` vit dans backend/, pas dans la racine du dossier de livraison.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Le .env de deploiement est a la racine du dossier livre (et non dans
# backend/), on le charge avant tout import de la configuration : il peut
# contenir DATABASE_URL, que le script doit respecter.
_ENV = BACKEND_DIR.parent / ".env"
if _ENV.is_file():
    from dotenv import load_dotenv

    load_dotenv(_ENV, override=False)

from app.core.config import build_postgres_dsn, get_settings  # noqa: E402

TIMEOUT = 10

CAUSES_CONNEXION = [
    "le service PostgreSQL n'est pas demarre",
    "  (Windows : services.msc -> PostgreSQL -> Demarrer, demarrage Automatique)",
    "le port indique n'est pas le bon : verifiez POSTGRES_PORT ou DATABASE_URL",
    "  (le port reel se lit dans les proprietes du service PostgreSQL)",
    "le pare-feu bloque le port (Pare-feu Windows Defender -> Connexions entrantes)",
]

CAUSES_AUTH = [
    "POSTGRES_USER / POSTGRES_PASSWORD ne correspondent pas au role existant",
    "le role n'a pas le droit de se connecter (regle pg_hba.conf)",
]

CAUSES_BASE = [
    "la base n'existe pas encore",
    "  (CREATE DATABASE <nom> OWNER <role>;  cf. README section 3, etape 0)",
    "le role n'est pas proprietaire de la base",
]


def build_target() -> tuple[str, dict]:
    """Meme resolution que migrate.py et app.db.database : DATABASE_URL gagne,
    sinon on reconstruit depuis POSTGRES_*. Sans cela, un .env qui ne definit
    que DATABASE_URL serait diagnostique sur une autre base que la bonne."""
    settings = get_settings()
    if settings.DATABASE_URL:
        url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        return url, {}

    return (
        build_postgres_dsn(settings),
        {
            "host": settings.POSTGRES_HOST,
            "port": int(settings.POSTGRES_PORT or 5432),
            "dbname": settings.POSTGRES_DB,
            "user": settings.POSTGRES_USER,
            "password": settings.POSTGRES_PASSWORD,
        },
    )


def masked(url: str) -> str:
    """Masque le mot de passe avant toute impression dans une console ou un
    journal d'installation."""
    if "@" not in url or "://" not in url:
        return url
    head, _, tail = url.partition("@")
    scheme, _, rest = head.partition("://")
    user, sep, _pwd = rest.partition(":")
    return f"{scheme}://{user}{sep}***@{tail}" if sep else f"{scheme}://{user}@{tail}"


def endpoint(url: str, dsn: dict) -> str:
    return f"{dsn.get('host', '?')}:{dsn.get('port', '?')}" if dsn else url


def host_port(url: str, dsn: dict) -> tuple[str, int]:
    if dsn:
        return str(dsn.get("host", "localhost")), int(dsn.get("port", 5432))
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return parts.hostname or "localhost", parts.port or 5432


def tcp_reachable(host: str, port: int) -> bool:
    """Le port TCP est-il joignable ? Ne demande ni authentification ni base."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except OSError:
        return False


def classify(psycopg, url: str, dsn: dict) -> tuple[str, list[str]]:
    """Distingue les 3 pannes sans dependre de la langue du serveur.

    psycopg3 expose l'echec de connexion comme un OperationalError unique,
    SANS SQLSTATE : impossible de differencier 28P01 (mot de passe) de 3D000
    (base absente) en lisant le message, d'autant que celui-ci est traduit
    (lc_messages). Une installation PostgreSQL francaise repond
    "authentification par mot de passe echouee".

    On tranche donc par deux sondes factuelles :
      1. le port TCP repond-il ?  non -> service arrete / pare-feu / mauvais port
      2. le role se connecte-t-il a la base de maintenance `postgres` ?
         oui  -> identifiants valides, donc c'est la base cible qui manque
         non  -> identifiants refuses
    """
    host, port = host_port(url, dsn)

    if not tcp_reachable(host, port):
        return f"Connexion impossible a {host}:{port}", CAUSES_CONNEXION

    probe = dict(dsn) if dsn else {}
    if probe:
        probe["dbname"] = "postgres"
    else:
        # On remplace simplement le nom de base en fin d'URL, en conservant
        # scheme, identifiants, mot de passe, hote et port.
        probe_url = url.rsplit("/", 1)[0] + "/postgres"

    try:
        if probe:
            test = psycopg.connect(connect_timeout=TIMEOUT, **probe)
        else:
            test = psycopg.connect(probe_url, connect_timeout=TIMEOUT)
        test.close()
        return f"La base '{dbname_from(url, dsn)}' n'existe pas ou n'est pas accessible.", CAUSES_BASE
    except psycopg.Error:
        return "Authentification PostgreSQL refusee.", CAUSES_AUTH


def dbname_from(url: str, dsn: dict) -> str:
    """Nom de la base cible, pour un message d'erreur explicite."""
    if dsn:
        return str(dsn.get("dbname", "?"))
    return url.rstrip("/").rsplit("/", 1)[-1] or "?"


def main() -> int:
    try:
        import psycopg
    except ImportError:
        print(
            "  [ERREUR] psycopg absent : lancez d'abord install.bat "
            "(dependencies non installees).",
            file=sys.stderr,
        )
        return 1

    try:
        url, dsn = build_target()
    except Exception as exc:  # configuration invalide (secret manquant, .env casse)
        print(f"  [ERREUR] Configuration invalide : {exc}", file=sys.stderr)
        return 1

    print(f"  Cible : {masked(url)}")

    try:
        if dsn:
            conn = psycopg.connect(connect_timeout=TIMEOUT, **dsn)
        else:
            conn = psycopg.connect(url, connect_timeout=TIMEOUT)
    except psycopg.OperationalError as exc:
        text = str(exc).strip()
        headline, causes = classify(psycopg, url, dsn)

        print(f"  [ERREUR] {headline}", file=sys.stderr)
        print("", file=sys.stderr)
        for line in causes:
            print(f"               - {line}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"               {text.splitlines()[0]}", file=sys.stderr)
        print("", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"  [ERREUR] Connexion refusee : {exc}", file=sys.stderr)
        return 1

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0].split(",")[0]
            cur.execute("SELECT current_database(), current_user")
            base, role = cur.fetchone()
            cur.execute(
                "SELECT has_database_privilege(current_database(), 'CREATE')"
            )
            can_create = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            tables = cur.fetchone()[0]

    print(f"  [OK] Serveur  : {version}")
    print(f"  [OK] Base     : {base}")
    print(f"  [OK] Role     : {role} ({'peut creer des objets' if can_create else 'PAS de droit CREATE'})")
    print(f"  [OK] Tables   : {tables}")

    if not can_create:
        print("", file=sys.stderr)
        print("  [ERREUR] Le role n'a pas le droit CREATE sur cette base :", file=sys.stderr)
        print("          les migrations echoueront.", file=sys.stderr)
        print("          ALTER DATABASE <base> OWNER TO <role>;", file=sys.stderr)
        return 1

    if tables:
        print("")
        print("  [i] La base contient deja des tables.")
        print("      install.bat peut reprendre : les migrations deja appliquees")
        print("      seront ignorees. Pour repartir de zero, videz la base.")
    else:
        print("")
        print("  [i] Base vide : install.bat va creer tout le schema.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())