import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "DYNDISPLAY_DEV"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""

    SFTP_HOST: str = "localhost"
    SFTP_PORT: int = 22
    SFTP_USERNAME: str = ""
    SFTP_PASSWORD: str = ""
    SFTP_ROOT_PATH: str = ""

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Durée de vie du token de RENOUVELLEMENT (typ=refresh). Le token d'accès
    # expire au bout de 30 min : sans refresh, une session laissée ouverte se
    # transforme en cascade de 401 (une par requête déjà partie). Le refresh
    # permet de renouveler l'accès sans ressaisir le mot de passe.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Durée de vie des tokens MÉDIAS (GET /media/{path} + balises <img>/<video>).
    # Token dédié, scopé à UN seul fichier média, distinct du token de session :
    # il circule dans l'URL (?token=) et doit donc rester court vécu (suffisant
    # pour charger/afficher un média, jamais un accès permanent ni un équivalent
    # de session). Voir app/core/security.create_media_token.
    MEDIA_TOKEN_EXPIRE_MINUTES: int = 60

    CORS_ORIGINS: str = "http://localhost:5173"

    MEDIA_ROOT: str = "./media_storage"

    # Dossier contenant le frontend compilé (servi par le backend en mode production Web).
    UI_DIST_PATH: str = ""

    # Nombre maximal de jobs de sync exécutés EN PARALLÈLE (executor borné +
    # pool de connexions dédié gesto-sync dimensionné à cette valeur). Au-delà,
    # les jobs attendent dans la file : ils restent PENDING/SCHEDULED et sont
    # exclus de la reprise des orphelins tant qu'ils sont en file/en cours.
    # Réglage clé contre la saturation PostgreSQL (max_connections) pendant
    # l'orage d'auto-sync multi-tenant.
    SYNC_MAX_WORKERS: int = 8

    # Suffixe secret du code d'accès Admin suprême (JJMMAAAA + ce suffixe).
    # Aucune valeur par défaut : le serveur refuse de démarrer si elle est
    # absente/vide (fail-fast, validator _supreme_admin_secret_required).
    # Ne jamais committer la vraie valeur — elle n'existe que dans le .env.
    SUPREME_ADMIN_SECRET: str = ""

    # --- Réseau (lecture par install-helpers/serve.py, qui passe --host/--port
    # à uvicorn) ---
    # Déclarés ici pour que le .env livré soit intégralement décrit par ce
    # modèle : pydantic-settings rejette par défaut toute clé inconnue du
    # .env, et une clé annoncée dans .env.example mais absente de Settings
    # faisait tomber l'application au premier chargement.
    DYNDISPLAY_HOST: str = "0.0.0.0"
    DYNDISPLAY_PORT: int = 8000

    # Fuseau horaire de l'application (vide = heure locale du serveur).
    APP_TIMEZONE: str = ""

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _jwt_secret_required(cls, v: str) -> str:
        # Pas de valeur par défaut silencieuse pour un secret de signature :
        # un secret vide (ou absent) ferait des tokens forgeables. Fail-fast.
        if not v.strip():
            raise ValueError(
                "JWT_SECRET_KEY n'est pas défini : impossible de signer les tokens "
                "d'authentification (faille de sécurité majeure). Générez une valeur "
                "forte (ex. `openssl rand -hex 32`), définissez-la dans .env, et ne "
                "la committez jamais."
            )
        return v

    @field_validator("SUPREME_ADMIN_SECRET")
    @classmethod
    def _supreme_admin_secret_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "SUPREME_ADMIN_SECRET n'est pas défini : le code d'accès Admin suprême "
                "vaut JJMMAAAA + ce suffixe secret. Définissez-le dans .env "
                "(ex. X7K9, à rallonger en production)."
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

        # Une clé inconnue dans .env ne doit pas rendre le serveur
        # inexploitable. Le .env est écrit et relu à la main par
        # l'exploitant, et install.bat CONSERVE un .env existant : sans cette
        # tolérance, une mise à jour depuis une version antérieure (qui a pu
        # laisser des clés devenues inutiles) arrête le démarrage sur une
        # traceback pydantic incompréhensible, sans distinguer une vraie erreur
        # de configuration d'un simple reliquat.
        # Les secrets critiques restent protégés par leurs validators
        # (JWT_SECRET_KEY, SUPREME_ADMIN_SECRET) : une clé mal orthographiée
        # est ici ignorée, donc ces valeurs retombent sur "" et le fail-fast
        # démarre quand même.
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def build_postgres_dsn(settings: Settings | None = None) -> str:
    """Construit le DSN PostgreSQL a partir des champs POSTGRES_*.

    L'identifiant et le mot de passe sont percent-encodes. Sans cela, un mot
    de passe contenant un caractere reserve d'URL casse silencieusement la
    connexion :

        postgresql://u:Dyn#123@h:5432/db   ->  '#' ouvre le fragment
        => l'URL est coupee en  postgresql://u:Dyn
        => le mot de passe vu par libpq ne contient plus le reste.

    Ce n'est pas theorique : le generateur de l'installateur produit des
    mots de passe contenant '#' et '%', donc une installation neuve pouvait se
    retrouver incapable de se connecter a sa propre base alors que psql, lui,
    fonctionnait avec le meme mot de passe. Le symptome (authentification
    echouee pour l'utilisateur X) ne designait aucun mot de passe errone.

    DATABASE_URL, si elle est renseignee, reste prioritaire et n'est jamais
    reecrite ici : elle appartient a l'exploitant, qui y met lui-meme les
    bons caracteres d'echappement.
    """
    from urllib.parse import quote

    settings = settings or get_settings()
    return (
        f"postgresql://{quote(settings.POSTGRES_USER, safe='')}:"
        f"{quote(settings.POSTGRES_PASSWORD, safe='')}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/"
        f"{quote(settings.POSTGRES_DB, safe='')}"
    )
