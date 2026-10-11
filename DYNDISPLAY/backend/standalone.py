"""Point d'entrée du binaire compilé DynDisplay.

Ce module est le SEUL exécuté par Nuitka. Il fait trois choses et delegates
le reste à l'application existante, sans rien dupliquer :

  1. charge la configuration (fichier .env à côté du binaire, ou variables
     d'environnement) ;
  2. lance uvicorn sur l'hôte/port demandés ;
  3. reste bloquant.

Pourquoi un module dédié plutôt que `python -m uvicorn app.main:app` : le binaire
doit se lancer tout seul, sans interpréteur ni ligne de commande à saisir.
"""

from __future__ import annotations

import os
import sys


def _default_env_path() -> str | None:
    """Recherche le .env à côté du binaire compilé."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(base, ".env")
    return candidate if os.path.isfile(candidate) else None


def main() -> int:
    env_path = _default_env_path()
    if env_path:
        # Charge SANS écraser les variables déjà présentes : un déploiement peut
        # surcharger une valeur via l'environnement du service.
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)

    import uvicorn

    host = os.environ.get("DYNDISPLAY_HOST", "127.0.0.1")
    port = int(os.environ.get("DYNDISPLAY_PORT", "8000"))
    log_level = os.environ.get("DYNDISPLAY_LOG_LEVEL", "info")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=log_level,
        # workers=1 : la licence est en base et le rate limit est en mémoire.
        # Plusieurs workers compliqueraient les deux sans gain ici.
        workers=1,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
