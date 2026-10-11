"""Configuration des tests — base de données DEDIEE et garde-fous.

REGLE STRUCTURANTE
------------------
Les tests backend ne doivent JAMAIS toucher la base de production ni le compte
admin de production. Deux garde-fous :

1. Les tests lisent `backend/.env.test` (et non `backend/.env`) : la base de
   test est physiquement distincte.
2. `assert_test_db_url()` REFUSE toute URL qui ne contient pas le suffixe
   "_test". Appele au chargement de `tests/conftest.py`, il fait echouer la
   collecte pytest AVANT qu'un seul test ne soit execute si la variable
   d'environnement pointe par erreur sur la base reelle.

Aucune valeur par defaut n'est toleree : si une variable obligatoire manque,
le test echoue explicitement plutot que de silencieusement utiliser un compte
partage.
"""

import os
import pathlib

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
TEST_ENV_FILE = BACKEND_DIR / ".env.test"

# Sous-chaine obligatoire dans l'URL de la base de test.
REQUIRED_DB_MARKER = "_test"


class TestConfigError(RuntimeError):
    """Configuration de test invalide : les tests ne doivent pas demarrer."""


def _read_env_file(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _require(marker: str, env_var: str, env_file_value: str | None) -> str:
    value = env_var or env_file_value
    if not value:
        raise TestConfigError(
            f"Configuration de test incomplete : {marker} est absente.\n"
            f"  - soit definez la variable d'environnement {marker} ;\n"
            f"  - soit renseignez-la dans {TEST_ENV_FILE.name} "
            f"({TEST_ENV_FILE}).\n"
            f"Aucun repli par defaut n'est applique : les tests ne doivent jamais "
            f"utiliser un identifiant partage."
        )
    return value


def get_test_db_url() -> str:
    """URL PostgreSQL de la base de tests, verifiee non destructive."""
    env_file = _read_env_file(TEST_ENV_FILE)
    url = (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or env_file.get("DATABASE_URL")
    )
    if not url:
        raise TestConfigError(
            "Aucune URL de base de tests trouvee.\n"
            f"  - soit definissez TEST_DATABASE_URL ;\n"
            f"  - soit completez DATABASE_URL dans {TEST_ENV_FILE} "
            f"({TEST_ENV_FILE})."
        )
    return url


def assert_test_db_url(url: str) -> None:
    """Garde-fou : echoue si l'URL ne cible pas une base de test.

    C'est la protection contre la destruction de la base de production : sans
    ce controle, un `DATABASE_URL` oublie dans l'environnement ferait ecrire
    les tests directement sur les donnees reelles.
    """
    lowered = url.lower()
    if REQUIRED_DB_MARKER not in lowered:
        raise TestConfigError(
            "BLOQUANT — les tests refuses de demarrer.\n"
            f"  URL de base fournie : {url}\n"
            f"  Elle ne contient pas le suffixe obligatoire "
            f"'{REQUIRED_DB_MARKER}'.\n"
            "  Les tests ne doivent JAMAIS toucher la base de production ni le "
            "compte admin reel.\n"
            f"  Corriger : utiliser {TEST_ENV_FILE.name} ou definir "
            f"TEST_DATABASE_URL avec une base ...{REQUIRED_DB_MARKER}."
        )


def get_test_admin_password() -> str:
    """Mot de passe du compte admin de la base de TEST.

    Plus aucun repli du type "admin123" : une variable absente doit faire
    echouer le test, pas le faire passer avec un mot de passe arbitraire qui
    masquerait une base mal initialisee.
    """
    env_file = _read_env_file(TEST_ENV_FILE)
    return _require(
        "TEST_ADMIN_PASSWORD",
        os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("SEED_ADMIN_PASSWORD") or "",
        env_file.get("TEST_ADMIN_PASSWORD"),
    )


def get_base_url() -> str:
    env_file = _read_env_file(TEST_ENV_FILE)
    return (
        os.environ.get("TEST_BASE_URL")
        or env_file.get("TEST_BASE_URL")
        or "http://localhost:8000"
    )