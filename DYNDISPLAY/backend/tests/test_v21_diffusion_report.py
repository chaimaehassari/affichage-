import time
import uuid

import pytest
import requests
import psycopg

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_db_url

DB_URL = get_test_db_url()
TEST_PASSWORD = "Test@1234"
DEVICE_ID = "pytest-device-drf-0001"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


@pytest.mark.v21
class TestDiffusionReport:
    """Rapport de diffusion (Admin Client).

    GET /api/v1/clients/me/posts/diffusion-report

    - Le périmètre est déduit de la session (scope client) — jamais d'un
      paramètre de l'appelant.
    - Un poste d'un autre client est invisible, même si son post_id est forcé.
    - Le heartbeat accepte un champ `current_media` optionnel ; les postes hors
      ligne ne divulguent aucune donnée de diffusion obsolète.
    """

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _login(login: str, client_code: str | None = None) -> dict:
        body = {"login": login, "password": TEST_PASSWORD}
        if client_code:
            body["client_code"] = client_code
        r = _api("POST", "/api/v1/auth/login", json=body,
                 headers={"X-Device-Id": DEVICE_ID})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}",
                "X-Device-Id": DEVICE_ID}

    @staticmethod
    def _create_client_db(code: str) -> int:
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO clients (code_client, nom_client,
                                         license_sites, license_posts)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (code, f"Client {code}", 10, 20),
                )
                client_id = cur.fetchone()[0]
            conn.commit()
            return client_id
        finally:
            conn.close()

    @staticmethod
    def _create_admin_db(admin_headers: dict, code: str) -> dict:
        """Crée un Admin classique (rôle Admin Client) via POST /admins."""
        login = f"drfadmin_{_uid().lower()}"
        r = _api("POST", "/api/v1/admins", json={
            "user_code": code,
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "is_active": True,
        }, headers=admin_headers)
        assert r.status_code == 201, r.text
        admin = r.json()
        return admin

    @staticmethod
    def _assign(admin_headers: dict, admin_id: int, client_code: str) -> requests.Response:
        return _api("POST", f"/api/v1/admins/{admin_id}/clients",
                    json={"client_code": client_code}, headers=admin_headers)

    @staticmethod
    def _create_site_post(client_code: str, client_id: int):
        """Crée un site + un poste rattachés au client. Retourne (site_id, post_id)."""
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sites (code, name, address, description, is_active,
                                       client_code, client_id)
                    VALUES (%s, %s, '', '', TRUE, %s, %s)
                    RETURNING site_id
                    """,
                    (f"DRFSITE{_uid()}", f"Site {client_code}", client_code, client_id),
                )
                site_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO posts (site_id, code, name, is_active)
                    VALUES (%s, %s, %s, TRUE) RETURNING post_id
                    """,
                    (site_id, f"DRFPOST{_uid()}", f"Poste {client_code}"),
                )
                post_id = cur.fetchone()[0]
            conn.commit()
            return int(site_id), int(post_id)
        finally:
            conn.close()

    @staticmethod
    def _create_media(client_code: str, media_type: str, sftp_path: str) -> int:
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO media (name, original_filename, media_type, mime_type,
                                       file_extension, file_size, sftp_path, checksum,
                                       is_active, client_code, page_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                    RETURNING media_id
                    """,
                    (f"Média {media_type}", f"m_{_uid().lower()}.ext", media_type,
                     "application/octet-stream", "ext", 1024, sftp_path,
                     uuid.uuid4().hex, client_code,
                     3 if media_type == "PDF" else None),
                )
                media_id = cur.fetchone()[0]
            conn.commit()
            return int(media_id)
        finally:
            conn.close()

    @staticmethod
    def _heartbeat(post_id: int, current_media=None) -> requests.Response:
        body = {"post_id": post_id}
        if current_media is not None:
            body["current_media"] = current_media
        return _api("POST", "/api/v1/posts/heartbeat", json=body)

    @staticmethod
    def _current_media_columns(post_id: int, expected: tuple, timeout: float = 5.0):
        """Relit current_media_* en attendant l'état attendu.

        FastAPI renvoie la réponse AVANT la fin du teardown de la dépendance
        `get_db` (qui porte le COMMIT) : un `200` suivi d'une lecture sur une
        autre connexion peut donc observer l'état précédent pendant quelques
        millisecondes. On patiente un court délai au lieu d'exposer une course
        au test ; le dernier état lu est renvoyé pour un diagnostic clair.
        """
        deadline = time.time() + timeout
        while True:
            conn = psycopg.connect(DB_URL)
            try:
                row = conn.execute(
                    "SELECT current_media_name, current_media_type, current_media_id "
                    "FROM posts WHERE post_id = %s",
                    (post_id,),
                ).fetchone()
            finally:
                conn.close()
            if row == expected or time.time() >= deadline:
                return row
            time.sleep(0.2)

    @staticmethod
    def _report(headers: dict, post_id: int | None = None) -> requests.Response:
        path = "/api/v1/clients/me/posts/diffusion-report"
        if post_id is not None:
            path += f"?post_id={post_id}"
        return _api("GET", path, headers=headers)

    @staticmethod
    def _cleanup(client_codes=(), user_ids=(), media_ids=()):
        if not (client_codes or user_ids or media_ids):
            return
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                if media_ids:
                    cur.execute("DELETE FROM media WHERE media_id = ANY(%s)", (list(media_ids),))
                if client_codes:
                    cur.execute(
                        "DELETE FROM posts p USING sites s "
                        "WHERE p.site_id = s.site_id AND s.client_code = ANY(%s)",
                        (list(client_codes),),
                    )
                    cur.execute("DELETE FROM sites WHERE client_code = ANY(%s)", (list(client_codes),))
                if user_ids:
                    cur.execute("DELETE FROM users WHERE user_id = ANY(%s)", (list(user_ids),))
                if client_codes:
                    cur.execute("DELETE FROM clients WHERE code_client = ANY(%s)", (list(client_codes),))
            conn.commit()
        finally:
            conn.close()

    # --- 1) Isolation des clients + contenus affichés ----------------------

    def test_diffusion_report_isolates_clients_and_shows_media(self, admin_headers):
        cla = f"DRFA{_uid()}"
        clb = f"DRFB{_uid()}"
        cla_id = self._create_client_db(cla)
        clb_id = self._create_client_db(clb)
        admin = None
        media_ids = []
        try:
            admin = self._create_admin_db(admin_headers, f"DRADM{_uid()}")
            assert self._assign(admin_headers, admin["user_id"], cla).status_code == 201
            ah = self._login(admin["login"])

            _, a1 = self._create_site_post(cla, cla_id)
            _, a2 = self._create_site_post(cla, cla_id)
            _, a3 = self._create_site_post(cla, cla_id)  # jamais de heartbeat
            _, b1 = self._create_site_post(clb, clb_id)

            img_path = f"images/{_uid().lower()}.png"
            img = self._create_media(cla, "IMAGE", img_path)
            media_ids.append(img)

            # `media.sftp_path` est UNIQUE : le timestamp doit être unique par
            # run, tout en gardant la convention `pdfs/<ts>_<nom>.pdf` parsée
            # par SupervisionService._pdf_page1_path.
            pdf_ts = str(1750000000 + int(_uid(), 16) % 100000)
            pdf = self._create_media(cla, "PDF", f"pdfs/{pdf_ts}_guide.pdf")
            media_ids.append(pdf)

            # Players (heartbeat SANS auth) : A1 diffuse une IMAGE, A2 un PDF,
            # B1 envoie un heartbeat sans média (rien à afficher).
            assert self._heartbeat(a1, current_media={
                "media_id": img,
                "name": "Promo été",
                "media_type": "IMAGE",
                "zone_number": 0,
                "started_at": "2026-09-23T08:00:00Z",
            }).status_code == 200
            assert self._heartbeat(a2, current_media={
                "media_id": pdf,
                "name": "Manuel.pdf",
                "media_type": "PDF",
                "started_at": "2026-09-23T08:05:00+02:00",
            }).status_code == 200
            assert self._heartbeat(b1).status_code == 200

            r = self._report(ah)
            assert r.status_code == 200, r.text
            posts = {p["post_id"]: p for p in r.json()["posts"]}

            # Isolation totale : aucun poste du client B.
            assert b1 not in posts
            for p in posts.values():
                assert p["site_name"] != f"Site {clb}"

            # A1 : en ligne, IMAGE, miniature = sftp_path du média.
            pa = posts[a1]
            assert pa["is_online"] is True
            assert pa["current_media_name"] == "Promo été"
            assert pa["current_media_type"] == "IMAGE"
            assert pa["thumbnail_path"] == img_path
            assert pa["current_media_started_at"] is not None

            # A2 : PDF → miniature dérivée (page 1 rendue à l'upload).
            pb = posts[a2]
            assert pb["is_online"] is True
            assert pb["current_media_type"] == "PDF"
            assert pb["thumbnail_path"] == f"pdfs/{pdf_ts}_page_1.png"

            # A3 : jamais en ligne → hors ligne, aucune donnée de diffusion.
            pc = posts[a3]
            assert pc["is_online"] is False
            assert pc["thumbnail_path"] is None

            # Le Super Admin, lui, voit les deux clients.
            r = self._report(admin_headers)
            seen = {p["post_id"] for p in r.json()["posts"]}
            assert a1 in seen and b1 in seen
        finally:
            self._cleanup(client_codes=[cla, clb], media_ids=media_ids,
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 2) Un post_id d'un autre client ne fuite jamais -------------------

    def test_diffusion_report_foreign_post_id_never_leaks(self, admin_headers):
        cla = f"DRFA{_uid()}"
        clb = f"DRFB{_uid()}"
        cla_id = self._create_client_db(cla)
        clb_id = self._create_client_db(clb)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers, f"DRADM{_uid()}")
            assert self._assign(admin_headers, admin["user_id"], cla).status_code == 201
            ah = self._login(admin["login"])

            _, a1 = self._create_site_post(cla, cla_id)
            _, b1 = self._create_site_post(clb, clb_id)

            # Poste du client B forcé dans la requête → échec, aucune donnée.
            r = self._report(ah, post_id=b1)
            assert r.status_code in (403, 404), r.text
            assert "post_name" not in r.text

            # Poste inexistant → 404 également (pas de fuite d'existence).
            r = self._report(ah, post_id=99999999)
            assert r.status_code in (403, 404), r.text

            # Son propre poste est renvoyé normalement.
            r = self._report(ah, post_id=a1)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 1
            assert body["posts"][0]["post_id"] == a1
        finally:
            self._cleanup(client_codes=[cla, clb],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 3) Authentification requise ---------------------------------------

    def test_diffusion_report_requires_auth(self):
        r = self._report({})
        assert r.status_code == 401, r.text

    # --- 4) Heartbeat : current_media optionnel + validation ----------------

    def test_heartbeat_current_media_optional_clears_and_validates(self, admin_headers):
        cl = f"DRFC{_uid()}"
        cl_id = self._create_client_db(cl)
        admin = None
        media_ids = []
        try:
            admin = self._create_admin_db(admin_headers, f"DRADM{_uid()}")
            assert self._assign(admin_headers, admin["user_id"], cl).status_code == 201

            _, post_id = self._create_site_post(cl, cl_id)
            img_path = f"images/{_uid().lower()}.png"
            img = self._create_media(cl, "IMAGE", img_path)
            media_ids.append(img)

            conn = psycopg.connect(DB_URL)
            try:
                # Heartbeat avec média → colonnes positionnées.
                assert self._heartbeat(post_id, current_media={
                    "name": "Visuel",
                    "media_type": "IMAGE",
                    "media_id": img,
                    "started_at": "2026-09-23T08:10:00Z",
                }).status_code == 200
                row = self._current_media_columns(
                    post_id, ("Visuel", "IMAGE", img))
                assert row == ("Visuel", "IMAGE", img)

                # Heartbeat SANS current_media → rien à afficher (colonnes NULL).
                assert self._heartbeat(post_id).status_code == 200
                assert self._current_media_columns(
                    post_id, (None, None, None)) == (None, None, None)

                # current_media vide exploitable (player qui ne diffuse rien).
                assert self._heartbeat(post_id, current_media={}).status_code == 200

                # Type invalide → rejeté (422).
                r = self._heartbeat(post_id, current_media={"media_type": "TEXTE"})
                assert r.status_code == 422, r.text

                conn.commit()
            finally:
                conn.close()

            # Poste inconnu → 404.
            r = self._heartbeat(99999999)
            assert r.status_code == 404, r.text
        finally:
            self._cleanup(client_codes=[cl], media_ids=media_ids,
                          user_ids=[admin["user_id"]] if admin else [])