"""Configuration des tests (base de données locale) — sans secrets en dur.

L'URL PostgreSQL et le mot de passe du compte admin bootstrap ne sont jamais
committés en clair dans les sources de test :

1. Variable d'environnement `TEST_DATABASE_URL` si définie ;
2. Sinon, lecture de `backend/.env` (fichier NON committé, gitignoré) qui
   contient les valeurs de la machine de dev ;
3. Sinon, échec avec un message clair.

Le mot de passe admin suit `TEST_ADMIN_PASSWORD`, puis `SEED_ADMIN_PASSWORD`
(la même variable lue par seed_admin.py / seed_data.py), puis repli sur
"admin123" pour compatibilité avec une base déjà seedisée avant la sécurisation
des scripts de seed (comportement documenté, réservé au dev local).
"""

import os
import pathlib


def _read_backend_env() -> dict:
    env_path = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return {}
    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _build_db_url(values: dict) -> str:
    host = values.get("POSTGRES_HOST") or "localhost"
    port = values.get("POSTGRES_PORT") or "5433"
    user = values.get("POSTGRES_USER") or "postgres"
    password = values.get("POSTGRES_PASSWORD") or ""
    db = values.get("POSTGRES_DB") or "DYNDISPLAY"
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def get_test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    values = _read_backend_env()
    if values.get("POSTGRES_PASSWORD"):
        return _build_db_url(values)
    raise RuntimeError(
        "TEST_DATABASE_URL non définie et backend/.env introuvable ou sans "
        "POSTGRES_PASSWORD : les tests nécessitent une base PostgreSQL locale. "
        "Définissez TEST_DATABASE_URL dans l'environnement."
    )


def get_test_admin_password() -> str:
    return (
        os.environ.get("TEST_ADMIN_PASSWORD")
        or os.environ.get("SEED_ADMIN_PASSWORD")
        or "admin123"
    )