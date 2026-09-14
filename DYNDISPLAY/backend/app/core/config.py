import os
from functools import lru_cache
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

    SUPREME_ADMIN_SECRET: str = ""

    # Fuseau horaire de l'application (vide = heure locale du serveur).
    APP_TIMEZONE: str = ""

    # Secret HMAC pour la validation des codes de licence (doit être identique
    # à celui de l'outil de référence Python et de l'app Android).
    # Charge uniquement depuis .env (jamais une valeur en dur dans le code).
    LICENSE_SECRET: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
