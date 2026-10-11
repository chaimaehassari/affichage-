"""Stockage des fichiers médias : SFTP si configuré, disque local sinon.

Pourquoi cette couche existe
----------------------------
Le stockage des médias était branché directement sur `SFTPClient`, alors que le
`.env` de déploiement présente SFTP comme OPTIONNEL (« Requis uniquement pour
la synchronisation des médias distants ») et livre les cinq variables
`SFTP_*` vides. Conséquence : une installation standard ne pouvait importer
aucun média, et le symptôme était trompeur —

    POST /api/v1/media/upload -> 503 « Erreur de stockage SFTP :
    Unable to connect to : [WinError 10049] ... »

L'hôte y est vide, parce que `SFTP_HOST` n'est pas défini : le message ne
parlait pas du serveur SFTP du client, il parlait d'une configuration absente.
`MEDIA_ROOT` existait déjà dans `Settings` et était créé au démarrage, mais
n'était lu par aucun module.

Cette couche choisit le backend à partir de la configuration réelle :

    SFTP configuré  -> SftpStore  (partage lu par les players)
    sinon           -> LocalStore (dossier MEDIA_ROOT)

`media.sftp_path` reste un CHEMIN RELATIF (`images/1712_photo.png`) dans les
deux cas : la racine est appliquée à la lecture/écriture, jamais stockée en
base. Aucune migration n'est nécessaire, et un passage ultérieur de local vers
SFTP ne change pas les lignes existantes.

La synchronisation et la supervision, elles, restent SFTP par nature : les
players (Android/Windows) lisent le partage. Elles ne sont pas affectedes.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from app.core.config import Settings, get_settings
from app.sftp.client import SFTPClient

CHUNK_SIZE = 256 * 1024


class StorageUnavailable(Exception):
    """Le stockage des médias est momentanément injoignable.

   Exception distincte des erreurs « métier » (400/404) et des erreurs de
    traitement du fichier (500), parce qu'elle justifie un 503 — et surtout
    parce qu'elle permet à l'appelant de distinguer une panne de stockage d'un
    fichier invalide.

    C'est exactement ce qui manquait à l'import d'un PDF : la conversion et
    l'écriture des pages rendues partageaient un seul `try`, si bien qu'une
    panne SFTP était rapportée comme « Erreur lors de la conversion du PDF »
    en 500. Les appels qui enveloppent conversion ET écriture attrapent donc
    `StorageUnavailable` AVANT `Exception`, et le code remonte en 503.
    """


class InvalidMediaPath(ValueError):
    """Chemin média hors du dossier de stockage (traversée de répertoire).

    `ValueError` parce que c'est un refus d'entrée, pas une panne : le
    translator HTTP doit le rendre en 400, pas en 503.
    """


def normalize_relative_path(relative_path: str) -> str:
    """Valide un chemin média RELATIF et le renvoie normalisé.

    Résolution LEXICALE : `..` est effacé sans jamais toucher le disque, donc
    une traversée est rejetée même si la cible n'existe pas. C'est nécessaire
    sur les deux backends : la racine SFTP n'est pas forcément un chroot (sur
    l'installation de référence, le serveur OpenSSH sert le disque `C:`
    entier), donc `../../Windows/...` y sortirait du dossier de médias.

    Normalise aussi les séparateurs : une base|win peut contenir un `\\`
    parasite qui, sous Windows, ferait sortir le chemin de son dossier.
    """
    if not relative_path or not relative_path.strip():
        raise InvalidMediaPath("Chemin média vide.")

    cleaned = relative_path.replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for part in PurePosixPath(cleaned).parts:
        if part == "/":
            continue
        if part == ".":
            continue
        if part == "..":
            if not parts:
                raise InvalidMediaPath(
                    "Chemin média hors du dossier de stockage."
                )
            parts.pop()
            continue
        parts.append(part)

    if not parts:
        raise InvalidMediaPath("Chemin média vide.")
    return "/".join(parts)


class MediaStore:
    """Contrat commun aux deux backends de stockage."""

    backend = "?"

    def write(self, relative_path: str, data: bytes) -> None:
        raise NotImplementedError

    def exists(self, relative_path: str) -> bool:
        raise NotImplementedError

    def remove(self, relative_path: str) -> bool:
        raise NotImplementedError

    def size(self, relative_path: str) -> int | None:
        raise NotImplementedError

    def stream(self, relative_path: str) -> Iterator[bytes]:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self) -> MediaStore:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class SftpStore(MediaStore):
    """Stockage SFTP. Utilise quand SFTP_HOST/USERNAME/ROOT_PATH sont définis."""

    backend = "sftp"

    def __init__(self, settings: Settings | None = None):
        self._root = (settings or get_settings()).SFTP_ROOT_PATH.rstrip("/")
        self._client: SFTPClient | None = None

    def __enter__(self) -> SftpStore:
        host = (get_settings().SFTP_HOST or "").strip()
        try:
            client = SFTPClient()
            client.connect()
        except Exception as e:
            # `host` est famously vide quand SFTP n'est pas configuré : le
            # nommer dans le message évite de faire croire à une panne réseau.
            raise StorageUnavailable(
                f"Connexion SFTP impossible (hôte « {host or 'non défini'} ») : {e}"
            ) from e
        self._client = client
        return self

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _remote(self, relative_path: str) -> str:
        return f"{self._root}/{normalize_relative_path(relative_path)}"

    def _require(self) -> SFTPClient:
        if self._client is None:
            raise StorageUnavailable("Stockage SFTP non connecté.")
        return self._client

    def write(self, relative_path: str, data: bytes) -> None:
        remote = self._remote(relative_path)
        try:
            self._require().upload_bytes(data, remote)
        except Exception as e:
            raise StorageUnavailable(f"Échec de l'écriture SFTP de {remote} : {e}") from e

    def exists(self, relative_path: str) -> bool:
        remote = self._remote(relative_path)
        try:
            return self._require().exists(remote)
        except Exception as e:
            raise StorageUnavailable(
                f"Échec de l'accès SFTP à {remote} : {e}"
            ) from e

    def remove(self, relative_path: str) -> bool:
        remote = self._remote(relative_path)
        try:
            return self._require().remove_file(remote)
        except Exception as e:
            raise StorageUnavailable(
                f"Échec de la suppression SFTP de {remote} : {e}"
            ) from e

    def size(self, relative_path: str) -> int | None:
        remote = self._remote(relative_path)
        try:
            return self._require().remote_file_size(remote)
        except Exception as e:
            raise StorageUnavailable(
                f"Échec de la lecture SFTP de {remote} : {e}"
            ) from e

    def stream(self, relative_path: str) -> Iterator[bytes]:
        # Le générateur est consommé APRÈS le retour de la route (c'est le
        # corps d'une StreamingResponse) : la connexion est donc ouverte ici,
        # quand le streaming démarre, et fermée à l'épuisement.
        remote = self._remote(relative_path)
        try:
            with SFTPClient() as sftp:
                with sftp.open_remote(remote, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        yield chunk
        except GeneratorExit:
            raise
        except Exception as e:
            raise StorageUnavailable(
                f"Échec de la lecture SFTP de {remote} : {e}"
            ) from e


class LocalStore(MediaStore):
    """Stockage sur disque, sous MEDIA_ROOT. Utilisé quand SFTP n'est pas configuré."""

    backend = "local"

    def __init__(self, settings: Settings | None = None):
        media_root = (settings or get_settings()).MEDIA_ROOT
        self._root = Path(media_root).expanduser()

    @property
    def root(self) -> Path:
        return self._root

    def _local_path(self, relative_path: str) -> Path:
        relative = normalize_relative_path(relative_path)
        # `resolve()` exige que la racine existe pour être canonique : on la
        # crée (install.bat / serve.py le font déjà, mais un démarrage à la
        # main peut l'avoir omise).
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise StorageUnavailable(
                f"Impossible de préparer le dossier de médias {self._root} : {e}"
            ) from e

        candidate = self._root.joinpath(*relative.split("/")).resolve()
        root_resolved = self._root.resolve()
        # Seconde barrière : même un chemin lexicalement sûr doit retomber
        # dans la racine (junctions Windows, liens symboliques).
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise InvalidMediaPath("Chemin média hors du dossier de stockage.")
        return candidate

    def write(self, relative_path: str, data: bytes) -> None:
        path = self._local_path(relative_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Écriture dans un fichier temporaire puis remplacement atomique :
            # une coupure au milieu de l'upload ne laisse pas un fichier
            # tronqué que l'aperçu web afficherait comme valide.
            tmp = path.with_name(f".{path.name}.part")
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError as e:
            raise StorageUnavailable(f"Échec de l'écriture de {path} : {e}") from e

    def exists(self, relative_path: str) -> bool:
        return self._local_path(relative_path).is_file()

    def remove(self, relative_path: str) -> bool:
        path = self._local_path(relative_path)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as e:
            raise StorageUnavailable(
                f"Échec de la suppression de {path} : {e}"
            ) from e

    def size(self, relative_path: str) -> int | None:
        path = self._local_path(relative_path)
        try:
            return path.stat().st_size
        except FileNotFoundError:
            return None
        except OSError as e:
            raise StorageUnavailable(
                f"Échec de la lecture de {path} : {e}"
            ) from e

    def stream(self, relative_path: str) -> Iterator[bytes]:
        path = self._local_path(relative_path)
        try:
            with open(path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    yield chunk
        except GeneratorExit:
            raise
        except FileNotFoundError as e:
            raise StorageUnavailable(f"Fichier média introuvable : {path}") from e
        except OSError as e:
            raise StorageUnavailable(
                f"Échec de la lecture de {path} : {e}"
            ) from e


def is_sftp_configured(settings: Settings | None = None) -> bool:
    """Vrai si les trois variables SFTP nécessaires au stockage sont définies.

    Les trois, pas seulement l'hôte : un hôte renseigné sans identifiants
    (ou sans racine) ne permet aucun échange de fichiers, et la panne
    resurfacerait à l'import avec un message qui accuse le réseau.
    """
    s = settings or get_settings()
    # `all(a and b and c)` serait un piège : la chaîne `and` court-circuite
    # sur la première valeur fausse, donc sur `''`, et `all('')` est VRAI
    # (chaîne vide = aucun élément). La fonction répondrait True même sans
    # aucune variable renseignée, et tout le repli local resterait injoignable.
    return all([
        (s.SFTP_HOST or "").strip(),
        (s.SFTP_USERNAME or "").strip(),
        (s.SFTP_ROOT_PATH or "").strip(),
    ])


def get_media_store(settings: Settings | None = None) -> MediaStore:
    """Retourne le store correspondant à la configuration, SFTP si possible."""
    if is_sftp_configured(settings):
        return SftpStore(settings)
    return LocalStore(settings)


def cleanup_partial_upload(store: MediaStore, relative_paths: list[str]) -> None:
    """Supprime les fichiers déjà écrits lors d'un upload interrompu.

    Sans cela, un PDF dont la 3e page échoue laisse ses 2 premières pages
    PNG sur le stockage alors qu'aucune ligne `media` ne les référence :
    des fichiers orphelins invisibles pour l'interface et jamais ramassés.
    Les erreurs sont ignorées : le nettoyage est un confort, pas une condition
    de réussite de la suppression métier.
    """
    for relative_path in reversed(relative_paths):
        try:
            store.remove(relative_path)
        except Exception:
            pass
