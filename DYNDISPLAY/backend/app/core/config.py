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

    CORS_ORIGINS: str = "http://localhost:5173"

    MEDIA_ROOT: str = "./media_storage"

    # Dossier contenant le frontend compilé (servi par le backend en mode production Web).
    UI_DIST_PATH: str = ""

    # Suffixe secret du code d'accès Admin suprême (JJMMAAAA + ce suffixe).
    # Aucune valeur par défaut : le serveur refuse de démarrer si elle est
    # absente/vide (fail-fast, validator _supreme_admin_secret_required).
    # Ne jamais committer la vraie valeur — elle n'existe que dans le .env.
    SUPREME_ADMIN_SECRET: str = ""

    # Fuseau horaire de l'application (vide = heure locale du serveur).
    APP_TIMEZONE: str = ""

    # Secret HMAC pour la validation des codes de licence (doit être identique
    # à celui de l'outil de référence Python et de l'app Android).
    # Charge uniquement depuis .env (jamais une valeur en dur dans le code).
    LICENSE_SECRET: str = ""

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
