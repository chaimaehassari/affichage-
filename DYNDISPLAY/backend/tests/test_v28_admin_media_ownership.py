"""Non-régression : un Admin Client voit TOUJOURS ses propres médias.

Bug d'origine : le listing des médias filtrait uniquement sur `client_code`.
Un Admin classique qui n'a pas exactement UN client ne peut pas rattacher son
upload à un code client (`client_scope_scalar` renvoie NULL), donc le média
était stocké en global (`client_code` NULL) et sortait du listing — l'admin
ajoutait un média et ne le voyait jamais apparaître dans sa bibliothèque.

La règle de visibilité d'un média est donc :
    média visible  <=>  client_code dans mon périmètre
                       OU owner_user_id = moi
Le recoupement par clients élargit la visibilité aux médias des AUTRES admins ;
il ne doit JAMAIS restreindre la visibilité de ses propres médias.

Ces tests passent par l'API HTTP (pas seulement un contrôle visuel) et
interrogent GET /api/v1/media juste après POST /api/v1/media/upload.
"""
import io
import struct
import uuid
import zlib

import psycopg
import pytest
import requests

from tests._test_config import get_test_db_url
from tests.conftest import (
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    TEST_DEVICE,
    login_as,
    make_headers,
)

_TEST_PWD = "Test@1234"


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)


BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _create_png():
    """PNG 1x1 minimal, avec des pixels aleatoires (checksum unique par appel)."""
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr = (struct.pack('>I', 13) + b'IHDR' + ihdr_data
            + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF))
    raw = zlib.compress(b'\x00\xff\x00\x00' + uuid.uuid4().bytes)
    idat = (struct.pack('>I', len(raw)) + b'IDAT' + raw
            + struct.pack('>I', zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF))
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND') & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


@pytest.mark.v28
class TestAdminSeesOwnMedia:

    @staticmethod
    def _create_client(code):
        """Cree un client en base (aucun endpoint de creation n'existe)."""
        conn = psycopg.connect(get_test_db_url())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO clients (code_client, nom_client,
                                         license_sites, license_posts)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (code, f"Client {code}", 10, 20),
                )
            conn.commit()
        finally:
            conn.close()
        return code

    def _create_admin(self, super_token, client_codes):
        """Cree un Admin classique et l'affecte a `client_codes` (liste vide = aucun)."""
        login = f"adm28_{_uid()}"
        payload = {
            "user_code": f"A28{_uid()}",
            "login": login,
            "password": _TEST_PWD,
            "password_confirm": _TEST_PWD,
            "is_active": True,
            "client_codes": list(client_codes),
        }
        r = _api("POST", "/api/v1/admins", json=payload, headers=make_headers(super_token))
        assert r.status_code == 201, r.text
        body = r.json()
        tok = _api("POST", "/api/v1/auth/login",
                   json={"login": login, "password": _TEST_PWD},
                   headers={"X-Device-Id": TEST_DEVICE})
        assert tok.status_code == 200, f"login admin: {tok.status_code} {tok.text}"
        # `clients` = périmètre RÉELLEMENT enregistré. Sans sélection explicite,
        # l'admin est auto-affecté à son propre client (cf. migration 024) : un
        # Admin classique n'a jamais un périmètre vide.
        return {"user_id": body["user_id"], "login": login,
                "headers": make_headers(tok.json()["access_token"]),
                "clients": body.get("client_codes") or list(client_codes),
                "auto_assigned_client": body.get("auto_assigned_client")}

    def _upload(self, headers):
        r = _api("POST", "/api/v1/media/upload", headers=headers,
                 files={"file": (f"v28_{_uid()}.png", io.BytesIO(_create_png()), "image/png")})
        assert r.status_code == 201, r.text
        return r.json()

    @staticmethod
    def _listed_ids(headers):
        r = _api("GET", "/api/v1/media", headers=headers)
        assert r.status_code == 200, r.text
        return {m["media_id"] for m in r.json()}

    def _delete_media_db(self, media_id):
        """Supprime le media en base : les admins de test n'ont pas forcement
        le droit de le supprimer (le client_code peut avoir ete libere entre-temps)."""
        conn = psycopg.connect(get_test_db_url())
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM media WHERE media_id = %s", (media_id,))
            conn.commit()
        finally:
            conn.close()

    def _delete_admins(self, super_token, admins):
        for a in admins:
            _api("DELETE", f"/api/v1/admins/{a['user_id']}", headers=make_headers(super_token))

    # MEDIA-OWN-1 : l'admin voit IMMEDIATEMENT le media qu'il vient d'uploader
    # (verifie via l'API, juste apres l'upload, pas via l'UI).
    def test_admin_sees_own_upload_immediately(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C28{_uid()}"
        self._create_client(code)
        admin = self._create_admin(token, [code])
        try:
            media = self._upload(admin["headers"])
            assert media["media_id"] > 0
            assert media["client_code"] == code, media

            ids = self._listed_ids(admin["headers"])
            assert media["media_id"] in ids, (
                f"le media {media['media_id']} uploade par l'admin "
                f"{admin['user_id']} est absent de son GET /api/v1/media : {ids}"
            )
        finally:
            self._delete_media_db(media["media_id"])
            self._delete_admins(token, [admin])

    # MEDIA-OWN-2 : un admin SANS aucun client voit ses propres uploads.
    # C'est le cas le plus net du bug : le media est stocke en global
    # (client_code NULL) et l'ancien filtre `AND 1 = 0` le faisait disparaitre.
    def test_admin_without_clients_sees_own_upload(self):
        # Un Admin créé SANS client sélectionné n'a plus de périmètre vide :
        # il est auto-affecté à son propre client (migration 024). Son upload
        # est donc rattaché à CE client, et non porté comme un média global
        # (client_code NULL) — c'est plus strict, pas moins.
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        admin = self._create_admin(token, [])
        try:
            assert len(admin["clients"]) == 1, admin
            media = self._upload(admin["headers"])
            assert media["client_code"] == admin["clients"][0], media

            ids = self._listed_ids(admin["headers"])
            assert media["media_id"] in ids, (
                f"un admin sans client ne voit pas son propre media : {ids}"
            )
        finally:
            self._delete_media_db(media["media_id"])
            self._delete_admins(token, [admin])

    # MEDIA-OWN-3 : un admin avec PLUSIEURS clients voit aussi ses uploads
    # (client_scope_scalar renvoie None -> media global, meme cas que ci-dessus).
    def test_admin_with_several_clients_sees_own_upload(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code_a, code_b = f"C28{_uid()}", f"C28{_uid()}"
        self._create_client(code_a)
        self._create_client(code_b)
        admin = self._create_admin(token, [code_a, code_b])
        try:
            media = self._upload(admin["headers"])
            assert media["client_code"] is None, media

            ids = self._listed_ids(admin["headers"])
            assert media["media_id"] in ids, (
                f"un admin multi-clients ne voit pas son propre media : {ids}"
            )
        finally:
            self._delete_media_db(media["media_id"])
            self._delete_admins(token, [admin])

    # MEDIA-OWN-4 : le recoupement par clients reste intact (Option B).
    #   * un 2e admin partageant le client voit le media ;
    #   * un 3e admin sans client commun ne le voit PAS.
    def test_shared_client_still_grants_visibility_and_isolation_holds(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        shared, other = f"C28{_uid()}", f"C28{_uid()}"
        self._create_client(shared)
        self._create_client(other)

        owner = self._create_admin(token, [shared])
        peer = self._create_admin(token, [shared])     # meme client
        stranger = self._create_admin(token, [other])  # aucun client commun
        admins = [owner, peer, stranger]
        try:
            media = self._upload(owner["headers"])
            assert media["client_code"] == shared, media
            mid = media["media_id"]

            assert mid in self._listed_ids(owner["headers"]), "l'auteur ne voit pas son media"
            assert mid in self._listed_ids(peer["headers"]), (
                "un admin partageant le client doit voir le media de l'autre admin"
            )
            assert mid not in self._listed_ids(stranger["headers"]), (
                "un admin sans client commun ne doit PAS voir ce media"
            )

            # Le media est aussi inaccessible en lecture directe pour l'etranger.
            assert _api("GET", f"/api/v1/media/{mid}", headers=stranger["headers"]).status_code == 404
            assert _api("GET", f"/api/v1/media/{mid}", headers=peer["headers"]).status_code == 200
        finally:
            self._delete_media_db(media["media_id"])
            self._delete_admins(token, admins)

    # MEDIA-OWN-5 : l'auteur peut supprimer son propre media meme sans client
    # (le chemin de suppression applique la meme regle de visibilite).
    def test_author_can_delete_own_media_without_clients(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        admin = self._create_admin(token, [])
        try:
            media = self._upload(admin["headers"])
            mid = media["media_id"]
            r = _api("DELETE", f"/api/v1/media/{mid}", headers=admin["headers"])
            assert r.status_code == 200, r.text
            assert mid not in self._listed_ids(admin["headers"])
        finally:
            self._delete_media_db(media["media_id"])
            self._delete_admins(token, [admin])
