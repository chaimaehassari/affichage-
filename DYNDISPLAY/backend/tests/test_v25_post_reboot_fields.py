import uuid

import pytest
import requests
import psycopg

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_db_url

DB_URL = get_test_db_url()


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


@pytest.mark.v25
class TestPostRebootFields:
    """Heure de redémarrage saisie dans le formulaire box (création / édition).

    POST /api/v1/posts et PUT /api/v1/posts/{post_id} acceptent désormais
    `reboot_enabled` + `reboot_time`, et renvoient ces champs pour que le
    formulaire se pré-remplisse en édition.

    Le déclencheur n'est pas un reboot immédiat : c'est l'échéance quotidienne
    calculée par le backend (`next_reboot_at`) que la synchronisation
    déclenchée par le frontend envoie ensuite à la box.
    """

    # --- Helpers ----------------------------------------------------------

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
    def _create_site_db(client_code: str, client_id: int) -> int:
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sites (code, name, address, description, is_active,
                                       client_code, client_id)
                    VALUES (%s, %s, '', '', TRUE, %s, %s) RETURNING site_id
                    """,
                    (f"RBTSITE{_uid()}", f"Site {client_code}", client_code, client_id),
                )
                site_id = cur.fetchone()[0]
            conn.commit()
            return int(site_id)
        finally:
            conn.close()

    @staticmethod
    def _create_post(headers: dict, site_id: int, **overrides) -> requests.Response:
        payload = {
            "site_id": site_id,
            "code": f"RBPOST{_uid()}",
            "name": "Box reboot",
            "player_type": "Windows",
            "ip_address": "10.0.0.9",
            "is_active": True,
        }
        payload.update(overrides)
        return _api("POST", "/api/v1/posts", json=payload, headers=headers)

    @staticmethod
    def _update_post(headers: dict, post_id: int, site_id: int, **overrides) -> requests.Response:
        payload = {
            "site_id": site_id,
            "code": f"RBUPD{_uid()}",
            "name": "Box reboot",
            "player_type": "Windows",
            "ip_address": "10.0.0.9",
            "is_active": True,
        }
        payload.update(overrides)
        return _api("PUT", f"/api/v1/posts/{post_id}", json=payload, headers=headers)

    @staticmethod
    def _reboot_row(post_id: int):
        conn = psycopg.connect(DB_URL)
        try:
            return conn.execute(
                "SELECT reboot_enabled, reboot_time, next_reboot_at "
                "FROM posts WHERE post_id = %s",
                (post_id,),
            ).fetchone()
        finally:
            conn.close()

    @staticmethod
    def _cleanup(client_code: str, post_ids=(), user_ids=()):
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                if post_ids:
                    cur.execute("DELETE FROM posts WHERE post_id = ANY(%s)", (list(post_ids),))
                cur.execute("DELETE FROM posts p USING sites s "
                            "WHERE p.site_id = s.site_id AND s.client_code = %s", (client_code,))
                cur.execute("DELETE FROM sites WHERE client_code = %s", (client_code,))
                if user_ids:
                    cur.execute("DELETE FROM users WHERE user_id = ANY(%s)", (list(user_ids),))
                cur.execute("DELETE FROM clients WHERE code_client = %s", (client_code,))
            conn.commit()
        finally:
            conn.close()

    # --- 1) Création avec heure -------------------------------------------

    def test_create_post_with_reboot_time(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            r = self._create_post(admin_headers, site_id,
                                  reboot_enabled=True, reboot_time="04:30")
            assert r.status_code == 201, r.text
            body = r.json()
            post_id = body["post_id"]

            # Le formulaire de création a bien enregistré le couple.
            assert body["reboot_enabled"] is True
            assert body["reboot_time"] == "04:30"
            assert body["next_reboot_at"] is not None

            # Persistance : heure + échéance calculée.
            enabled, reboot_time, next_reboot = self._reboot_row(post_id)
            assert enabled is True
            assert reboot_time.strftime("%H:%M") == "04:30"
            assert next_reboot is not None
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- 2) Création sans heure = pas de reboot ----------------------------

    def test_create_post_without_reboot_defaults_off(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            r = self._create_post(admin_headers, site_id)
            assert r.status_code == 201, r.text
            body = r.json()
            post_id = body["post_id"]
            assert body["reboot_enabled"] is False
            assert body["reboot_time"] is None
            assert body["next_reboot_at"] is None
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- 3) Activation sans heure = refus explicite ------------------------

    def test_enabled_without_time_is_rejected(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            # Jamais de reboot quotidien implicite à 00:00 : si l'admin
            # active le mécanisme, il doit choisir une heure.
            r = self._create_post(admin_headers, site_id, reboot_enabled=True)
            assert r.status_code == 400, r.text
            assert "heure" in r.text.lower()
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- 4) Heure invalide = 422 (validation de format) --------------------

    def test_invalid_reboot_time_is_rejected(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            for bad in ("25:00", "10h30", "abc"):
                r = self._create_post(admin_headers, site_id,
                                      reboot_enabled=True, reboot_time=bad)
                assert r.status_code == 422, (bad, r.text)
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- 5) Édition : changer l'heure, désactiver, réactiver --------------

    def test_update_reboot_time_then_disable_then_reenable(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            r = self._create_post(admin_headers, site_id,
                                  reboot_enabled=True, reboot_time="04:30")
            assert r.status_code == 201, r.text
            post_id = r.json()["post_id"]

            # Changement d'heure → nouvelle échéance.
            r = self._update_post(admin_headers, post_id, site_id,
                                  reboot_enabled=True, reboot_time="22:15")
            assert r.status_code == 200, r.text
            assert r.json()["reboot_time"] == "22:15"
            assert r.json()["next_reboot_at"] is not None
            _, reboot_time, _ = self._reboot_row(post_id)
            assert reboot_time.strftime("%H:%M") == "22:15"

            # Désactivation : l'heure est CONSERVÉE, l'échéance est annulée.
            r = self._update_post(admin_headers, post_id, site_id,
                                  reboot_enabled=False, reboot_time=None)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_enabled"] is False
            assert body["reboot_time"] == "22:15"
            assert body["next_reboot_at"] is None
            enabled, reboot_time, next_reboot = self._reboot_row(post_id)
            assert enabled is False
            assert reboot_time.strftime("%H:%M") == "22:15"
            assert next_reboot is None

            # Réactivation sans renvoyer d'heure → l'heure conservée repart.
            r = self._update_post(admin_headers, post_id, site_id, reboot_enabled=True)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_enabled"] is True
            assert body["reboot_time"] == "22:15"
            assert body["next_reboot_at"] is not None
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- 6) Les champs sont renvoyés pour pré-remplir le formulaire -------

    def test_get_post_exposes_reboot_fields(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            r = self._create_post(admin_headers, site_id,
                                  reboot_enabled=True, reboot_time="05:45")
            assert r.status_code == 201, r.text
            post_id = r.json()["post_id"]

            r = _api("GET", f"/api/v1/posts/{post_id}", headers=admin_headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_enabled"] is True
            assert body["reboot_time"] == "05:45"
            assert body["next_reboot_at"] is not None

            # Et dans la liste des postes (affichage du tableau des boxes).
            r = _api("GET", f"/api/v1/posts?site_id={site_id}", headers=admin_headers)
            assert r.status_code == 200, r.text
            listed = [p for p in r.json() if p["post_id"] == post_id]
            assert listed, r.text
            assert listed[0]["reboot_time"] == "05:45"
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- 7) Pas de fuite de configuration entre clients --------------------

    def test_group_admin_cannot_move_post_out_of_its_group(self, admin_headers):
        """Un admin de groupe ne peut pas greffer le reboot d'un poste sur un
        site d'un autre client (le scope protège aussi les nouveaux champs)."""
        cl_a = f"RBTA{_uid()}"
        cl_b = f"RBTB{_uid()}"
        cl_a_id = self._create_client_db(cl_a)
        cl_b_id = self._create_client_db(cl_b)
        site_a = self._create_site_db(cl_a, cl_a_id)
        site_b = self._create_site_db(cl_b, cl_b_id)
        admin = None
        post_id = None
        try:
            r = self._create_post(admin_headers, site_b,
                                  reboot_enabled=True, reboot_time="06:00")
            assert r.status_code == 201, r.text
            post_id = r.json()["post_id"]

            admin = self._create_admin_db(admin_headers, f"RBTADM{_uid()}")
            assert self._assign(admin_headers, admin["user_id"], cl_b).status_code == 201
            headers_b = self._login(admin["login"])

            # Déplacement vers le site du client A → refusé par le scope.
            r = self._update_post(headers_b, post_id, site_a, reboot_enabled=False)
            assert r.status_code == 400, r.text

            # Le poste garde son site et sa planification d'origine.
            r = _api("GET", f"/api/v1/posts/{post_id}", headers=admin_headers)
            assert r.status_code == 200, r.text
            assert r.json()["site_id"] == site_b
            assert r.json()["reboot_time"] == "06:00"
        finally:
            self._cleanup(cl_b, post_ids=[post_id] if post_id else [])
            self._cleanup(cl_a, user_ids=[admin["user_id"]] if admin else [])

    # --- 8) Contrôle du format de l'heure ----------------------------------

    def test_reboot_time_must_be_hh_mm(self, admin_headers):
        cl = f"RBT{_uid()}"
        cl_id = self._create_client_db(cl)
        site_id = self._create_site_db(cl, cl_id)
        post_id = None
        try:
            r = self._create_post(admin_headers, site_id,
                                  reboot_enabled=True, reboot_time="7:5")
            assert r.status_code == 422, r.text
        finally:
            self._cleanup(cl, post_ids=[post_id] if post_id else [])

    # --- Helpers supplémentaires -------------------------------------------

    @staticmethod
    def _create_admin_db(admin_headers: dict, code: str) -> dict:
        login = f"rbtadmin_{_uid().lower()}"
        r = _api("POST", "/api/v1/admins", json={
            "user_code": code,
            "login": login,
            "password": "Test@1234",
            "password_confirm": "Test@1234",
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
    def _login(login: str) -> dict:
        device = "pytest-device-rbt-0001"
        r = _api("POST", "/api/v1/auth/login",
                 json={"login": login, "password": "Test@1234"},
                 headers={"X-Device-Id": device})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}",
                "X-Device-Id": device}
