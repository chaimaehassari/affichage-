import uuid

import pytest
import requests
import psycopg

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_db_url

DB_URL = get_test_db_url()
TEST_PASSWORD = "Test@1234"
DEVICE_ID = "pytest-device-drf-0001"

# Route canonique du rapport + alias historique conservé (v21).
REPORT_PATH = "/api/v1/supervision/diffusion-report"
LEGACY_REPORT_PATH = "/api/v1/clients/me/posts/diffusion-report"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


@pytest.mark.v24
class TestDiffusionReportGroup:
    """Rapport de diffusion d'un admin de groupe (plusieurs clients).

    GET /api/v1/supervision/diffusion-report

    - L'admin voit TOUS les postes de TOUS les clients de son groupe, avec le
      client rattaché sur chaque ligne (l'ancien libellé « /clients/me/ »
      sous-entendait un client unique : il est trompeur pour un groupe).
    - Deux groupes ne se voient jamais, même via un `post_id` forcé.
    - Le verdict compare l'IDENTIFIANT du média réellement diffusé à celui des
      médias affectés : « à jour » / « pas encore changé ».
    """

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _login(login: str) -> dict:
        r = _api("POST", "/api/v1/auth/login",
                 json={"login": login, "password": TEST_PASSWORD},
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
                    INSERT INTO clients (code_client, nom_client, license_sites, license_posts)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (code, f"Client {code}", 10, 20),
                )
                client_id = cur.fetchone()[0]
            conn.commit()
            return int(client_id)
        finally:
            conn.close()

    @staticmethod
    def _create_admin_db(admin_headers: dict, code: str) -> dict:
        login = f"drgadmin_{_uid().lower()}"
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
    def _create_site_post(client_code: str, client_id: int, site_name: str = None) -> tuple:
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sites (code, name, address, description, is_active,
                                       client_code, client_id)
                    VALUES (%s, %s, '', '', TRUE, %s, %s) RETURNING site_id
                    """,
                    (f"DRGSITE{_uid()}", site_name or f"Site {client_code}",
                     client_code, client_id),
                )
                site_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO posts (site_id, code, name, is_active)
                    VALUES (%s, %s, %s, TRUE) RETURNING post_id
                    """,
                    (site_id, f"DRGPOST{_uid()}", f"Poste {client_code}"),
                )
                post_id = cur.fetchone()[0]
            conn.commit()
            return int(site_id), int(post_id)
        finally:
            conn.close()

    @staticmethod
    def _create_media(client_code: str, name: str) -> int:
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO media (name, original_filename, media_type, mime_type,
                                       file_extension, file_size, sftp_path, checksum,
                                       is_active, client_code)
                    VALUES (%s, %s, 'IMAGE', 'image/png', 'png', 1024, %s, %s,
                            TRUE, %s)
                    RETURNING media_id
                    """,
                    (name, f"m_{_uid().lower()}.png", f"images/{_uid().lower()}.png",
                     uuid.uuid4().hex, client_code),
                )
                media_id = cur.fetchone()[0]
            conn.commit()
            return int(media_id)
        finally:
            conn.close()

    @staticmethod
    def _assign_media_to_zone(post_id: int, media_id: int, zone_number: int = 1) -> None:
        """Affectation active sur une zone du poste (= ce qui est PROGRAMMÉ).

        `zone_number` est borné à 1..8 par `chk_zone_media_zone`.
        """
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO zone_media (post_id, zone_number, media_id,
                                            display_order, is_active)
                    VALUES (%s, %s, %s, 0, TRUE)
                    """,
                    (post_id, zone_number, media_id),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _heartbeat(post_id: int, current_media=None) -> requests.Response:
        body = {"post_id": post_id}
        if current_media is not None:
            body["current_media"] = current_media
        return _api("POST", "/api/v1/posts/heartbeat", json=body)

    @staticmethod
    def _report(headers: dict, path: str = REPORT_PATH, post_id: int | None = None):
        url = path
        if post_id is not None:
            url += f"?post_id={post_id}"
        return _api("GET", url, headers=headers)

    @staticmethod
    def _cleanup(client_codes=(), user_ids=(), media_ids=()):
        """Nettoyage : l'ordre compte.

        `zone_media` référence `posts` (CASCADE) et `media` (RESTRICT) : les
        affectations doivent disparaître AVANT les médias, sinon la suppression
        des médias est refusée par la clé étrangère.
        """
        if not (client_codes or user_ids or media_ids):
            return
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                if client_codes:
                    cur.execute(
                        "DELETE FROM zone_media zm USING posts p, sites s "
                        "WHERE zm.post_id = p.post_id AND p.site_id = s.site_id "
                        "AND s.client_code = ANY(%s)",
                        (list(client_codes),),
                    )
                if media_ids:
                    cur.execute(
                        "DELETE FROM zone_media WHERE media_id = ANY(%s)",
                        (list(media_ids),),
                    )
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

    # --- 1) Un admin de groupe voit TOUS les clients de son groupe --------

    def test_group_admin_sees_every_client_of_its_group(self, admin_headers):
        cla, clb = f"DRGA{_uid()}", f"DRGB{_uid()}"
        cla_id = self._create_client_db(cla)
        clb_id = self._create_client_db(clb)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers, f"DRGADM{_uid()}")
            # DEUX clients affectés au même admin : c'est le groupe.
            assert self._assign(admin_headers, admin["user_id"], cla).status_code == 201
            assert self._assign(admin_headers, admin["user_id"], clb).status_code == 201
            ah = self._login(admin["login"])

            _, pa1 = self._create_site_post(cla, cla_id)
            _, pa2 = self._create_site_post(cla, cla_id)
            _, pb1 = self._create_site_post(clb, clb_id)

            r = self._report(ah)
            assert r.status_code == 200, r.text
            body = r.json()
            posts = {p["post_id"]: p for p in body["posts"]}

            # Les deux clients du groupe sont dans le rapport…
            assert {pa1, pa2, pb1} <= set(posts)
            assert body["total"] == len(body["posts"])

            # …et chaque ligne porte le client de rattachement.
            assert posts[pa1]["client_code"] == cla
            assert posts[pa1]["client_name"] == f"Client {cla}"
            assert posts[pb1]["client_code"] == clb
            assert posts[pb1]["client_name"] == f"Client {clb}"

            # L'URL historique reste disponible et renvoie la même chose.
            legacy = self._report(ah, path=LEGACY_REPORT_PATH)
            assert legacy.status_code == 200, legacy.text
            assert {p["post_id"] for p in legacy.json()["posts"]} == set(posts)
        finally:
            self._cleanup(client_codes=[cla, clb],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 2) Verdict « à jour » / « pas encore changé » --------------------

    def test_diffusion_state_compares_assigned_and_actual_media(self, admin_headers):
        cl = f"DRGS{_uid()}"
        cl_id = self._create_client_db(cl)
        admin = None
        media_ids = []
        try:
            admin = self._create_admin_db(admin_headers, f"DRGADM{_uid()}")
            assert self._assign(admin_headers, admin["user_id"], cl).status_code == 201
            ah = self._login(admin["login"])

            programmed = self._create_media(cl, "Affiche programmée")
            other = self._create_media(cl, "Ancienne affiche")
            media_ids += [programmed, other]

            _, p_ok = self._create_site_post(cl, cl_id, "Site à jour")
            _, p_changed = self._create_site_post(cl, cl_id, "Site en retard")
            _, p_unknown = self._create_site_post(cl, cl_id, "Site sans retour")
            _, p_nomedia = self._create_site_post(cl, cl_id, "Site non programme")

            # Deux zones programmées sur le poste « à jour ».
            self._assign_media_to_zone(p_ok, programmed, zone_number=1)
            self._assign_media_to_zone(p_ok, other, zone_number=2)
            # Un seul média programmé sur le poste « en retard ».
            self._assign_media_to_zone(p_changed, programmed, zone_number=1)
            # p_unknown : média affecté mais le player n'a rien signalé.
            self._assign_media_to_zone(p_unknown, programmed, zone_number=1)
            # p_nomedia : aucune affectation.

            def media_payload(media_id: int, name: str) -> dict:
                return {"media_id": media_id, "name": name, "media_type": "IMAGE",
                        "zone_number": 1, "started_at": "2026-09-28T08:00:00Z"}

            assert self._heartbeat(p_ok, current_media=media_payload(programmed, "Affiche programmée")).status_code == 200
            assert self._heartbeat(p_changed, current_media=media_payload(other, "Ancienne affiche")).status_code == 200
            assert self._heartbeat(p_unknown).status_code == 200
            # p_nomedia : aucun heartbeat → hors ligne ET aucune affectation.

            r = self._report(ah)
            assert r.status_code == 200, r.text
            posts = {p["post_id"]: p for p in r.json()["posts"]}

            # À jour : le média diffusé fait partie des médias affectés.
            row = posts[p_ok]
            assert row["is_online"] is True
            assert row["diffusion_state"] == "up_to_date"
            assert row["is_up_to_date"] is True
            assert row["assigned_media_count"] == 2
            assert set(row["assigned_media_names"]) == {"Affiche programmée", "Ancienne affiche"}
            assert row["current_media_started_at"] is not None

            # Pas encore changé : la télé diffuse encore un média non affecté.
            row = posts[p_changed]
            assert row["is_online"] is True
            assert row["diffusion_state"] == "changed"
            assert row["is_up_to_date"] is False
            assert row["current_media_name"] == "Ancienne affiche"
            assert row["assigned_media_names"] == ["Affiche programmée"]

            # En ligne mais aucun média remonté → inconnu, PAS « à jour ».
            row = posts[p_unknown]
            assert row["is_online"] is True
            assert row["diffusion_state"] == "unknown"
            assert row["is_up_to_date"] is False
            assert row["current_media_name"] is None

            # Aucune affectation → rien à comparer, jamais « à jour ».
            row = posts[p_nomedia]
            assert row["assigned_media_count"] == 0
            assert row["diffusion_state"] in ("no_media", "offline")
            assert row["is_up_to_date"] is False
        finally:
            self._cleanup(client_codes=[cl], media_ids=media_ids,
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 3) Un poste hors ligne n'affiche aucun média obsolète ------------

    def test_offline_post_hides_stale_current_media(self, admin_headers):
        cl = f"DRGO{_uid()}"
        cl_id = self._create_client_db(cl)
        admin = None
        media_ids = []
        try:
            admin = self._create_admin_db(admin_headers, f"DRGADM{_uid()}")
            assert self._assign(admin_headers, admin["user_id"], cl).status_code == 201
            ah = self._login(admin["login"])

            media_id = self._create_media(cl, "Promo")
            media_ids.append(media_id)
            _, post_id = self._create_site_post(cl, cl_id)
            self._assign_media_to_zone(post_id, media_id)

            assert self._heartbeat(post_id, current_media={
                "media_id": media_id, "name": "Promo", "media_type": "IMAGE",
                "zone_number": 1, "started_at": "2026-09-28T08:00:00Z",
            }).status_code == 200

            # Heartbeat antidaté : le poste devient hors ligne alors que les
            # colonnes current_media* n'ont pas été purgées en base.
            conn = psycopg.connect(DB_URL)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE posts SET last_heartbeat_at = NOW() - INTERVAL '10 minutes' "
                        "WHERE post_id = %s",
                        (post_id,),
                    )
                conn.commit()
            finally:
                conn.close()

            r = self._report(ah, post_id=post_id)
            assert r.status_code == 200, r.text
            row = r.json()["posts"][0]
            assert row["is_online"] is False
            assert row["diffusion_state"] == "offline"
            assert row["is_up_to_date"] is False
            # Aucune donnée périmée ne fuite comme si elle était en cours.
            assert row["current_media_name"] is None
            assert row["current_media_started_at"] is None
            assert row["thumbnail_path"] is None
        finally:
            self._cleanup(client_codes=[cl], media_ids=media_ids,
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 4) Isolation entre deux groupes ----------------------------------

    def test_two_group_admins_never_see_each_other(self, admin_headers):
        cla, clb = f"DRGX{_uid()}", f"DRGY{_uid()}"
        cla_id = self._create_client_db(cla)
        clb_id = self._create_client_db(clb)
        admin_a = admin_b = None
        try:
            admin_a = self._create_admin_db(admin_headers, f"DRGADMA{_uid()}")
            admin_b = self._create_admin_db(admin_headers, f"DRGADMB{_uid()}")
            assert self._assign(admin_headers, admin_a["user_id"], cla).status_code == 201
            assert self._assign(admin_headers, admin_b["user_id"], clb).status_code == 201
            ha = self._login(admin_a["login"])
            hb = self._login(admin_b["login"])

            _, pa = self._create_site_post(cla, cla_id)
            _, pb = self._create_site_post(clb, clb_id)

            seen_a = {p["post_id"] for p in self._report(ha).json()["posts"]}
            seen_b = {p["post_id"] for p in self._report(hb).json()["posts"]}
            assert pa in seen_a and pb not in seen_a
            assert pb in seen_b and pa not in seen_b

            # post_id forcé vers le groupe adverse → refus, aucune fuite.
            r = self._report(ha, post_id=pb)
            assert r.status_code in (403, 404), r.text
            assert "Poste" not in r.text
        finally:
            self._cleanup(
                client_codes=[cla, clb],
                user_ids=[u["user_id"] for u in (admin_a, admin_b) if u],
            )

    # --- 5) Authentification requise ---------------------------------------

    def test_diffusion_report_requires_auth(self):
        r = self._report({})
        assert r.status_code == 401, r.text
