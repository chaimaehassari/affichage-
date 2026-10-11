"""Point d'entrée du binaire compilé DynDisplay.

Ce module est le seul exécuté au lancement. Il lance le serveur Uvicorn sur
l'application FastAPI existante, sans rien changer à son comportement.

Pourquoi un fichier séparé :
`app.main:app` est un objet applicatif, pas un point d'entrée exécutable. Le
binaire a besoin d'un `if __name__ == "__main__"` qui appelle `uvicorn.run()`.
Séparer les deux évite de polluer `app/main.py` — qui reste du code de
production testé — avec de la logique spécifique au packaging.

La configuration est lue AVANT le lancement pour distinguer deux erreurs
fréquentes sur un poste client :
  * configuration absente ou incomplète → message lisible ;
  * licence non configurée → avertissement explicite, le serveur démarre
    quand même pour que l'écran de sérialisation reste accessible.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _runtime_dir() -> Path:
    """Répertoire contenant l'exécutable, pour lire les fichiers voisins."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _configure_environment() -> Path | None:
    """Charge le .env adjacent à l'exécutable, s'il existe.

    Un serveur on-premise est installé dans un dossier dédié ; le `.env` est
    généré à l'installation (secrets aléatoires) et vit à côté du binaire.
    En développement, on retombe sur le comportement normal de pydantic.
    """
    env_path = _runtime_dir() / ".env"
    if env_path.is_file():
        os.environ["ENV_FILE"] = str(env_path)
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=str(env_path), override=True)
        except Exception:
            # pydantic-settings lit lui-même ENV_FILE ; load_dotenv est un
            # simple confort.
            pass
    return env_path if env_path.is_file() else None


def _warn_if_license_unconfigured() -> None:
    """Avertit si aucune clé publique de licence n'est configurée.

    Ne bloque PAS le démarrage : sans licence, le serveur doit tout de même
    répondre sur /health et sur les routes de sérialisation, pour que le client
    puisse lire son code machine. Le contrôle global des endpoints, prévu à
    l'étape suivante de la licence, refusera alors les autres.
    """
    try:
        from app.core.config import get_settings

        public_key = (get_settings().LICENSE_PUBLIC_KEY or "").strip()
    except Exception as exc:  # pragma: no cover
        print(f"[dyndisplay] configuration illisible : {exc}", file=sys.stderr)
        return

    if not public_key:
        print(
            "[dyndisplay] AVERTISSEMENT : LICENSE_PUBLIC_KEY absente.\n"
            "              Aucune licence ne pourra etre verifiee sur ce poste.",
            file=sys.stderr,
        )


def main() -> int:
    env_path = _configure_environment()
    runtime = _runtime_dir()

    print(f"[dyndisplay] repertoire d'execution : {runtime}")
    print(f"[dyndisplay] configuration         : {env_path or '(aucun .env adjacent)'}")

    _warn_if_license_unconfigured()

    host = os.environ.get("DYN_HOST", "127.0.0.1")
    port = int(os.environ.get("DYN_PORT", "8000"))
    # Hôte unique : ce backend n'est pas destiné à être exposé tel quel.
    # nginx ou IIS devant, avec TLS.
    print(f"[dyndisplay] demarrage sur http://{host}:{port}")

    import uvicorn

    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
