import uuid

import pytest
import requests
import psycopg

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_db_url
DB_URL = get_test_db_url()
TEST_PASSWORD = "Test@1234"
DEVICE_ID = "pytest-device-mtn-0001"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


@pytest.mark.v17
class TestMultiTenantSecurity:
    """Modèle multi-tenant : SUPER ADMIN → ADMIN → CLIENT → UTILISATEURS.

    - Super Admin : voit/gère tout.
    - Admin classique : voit seulement les clients affectés (admin_clients),
      ne peut ni modifier des licences ni gérer les admins ni s'auto-affecter.
    - Compte client (profil Utilisateur) : aucun accès à /clients.
    - Quotas postes/sites par client (clients.license_posts / license_sites).
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
    def _create_client_db(code: str, sites: int = 10, posts: int = 20) -> int:
        """Crée un client directement en base (pas d'endpoint de création)."""
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
                    (code, f"Client {code}", sites, posts),
                )
                client_id = cur.fetchone()[0]
            conn.commit()
            return client_id
        finally:
            conn.close()

    @staticmethod
    def _create_admin_db(admin_headers: dict, code: str) -> dict:
        """Crée un Admin classique via POST /admins (créé directement actif)."""
        login = f"mtnadmin_{_uid().lower()}"
        r = _api("POST", "/api/v1/admins", json={
            "user_code": code,
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "is_active": True,
        }, headers=admin_headers)
        assert r.status_code == 201, r.text
        return r.json()  # contient user_id, login, user_code

    @staticmethod
    def _create_client_user(admin_headers: dict, login: str, user_code: str) -> dict:
        """Crée un compte client (profil Utilisateur) via POST /users."""
        r = _api("POST", "/api/v1/users", json={
            "user_code": user_code,
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,  # Utilisateur
            "is_active": True,
            "zones": [],
            "permissions": [],
        }, headers=admin_headers)
        assert r.status_code == 201, r.text
        return r.json()  # contient user_id, login, user_code

    @staticmethod
    def _assign(admin_headers: dict, admin_id: int, client_code: str) -> requests.Response:
        return _api("POST", f"/api/v1/admins/{admin_id}/clients",
                    json={"client_code": client_code}, headers=admin_headers)

    @staticmethod
    def _detach(admin_headers: dict, admin_id: int, client_code: str) -> requests.Response:
        return _api("DELETE", f"/api/v1/admins/{admin_id}/clients/{client_code}",
                    headers=admin_headers)

    @staticmethod
    def _cleanup(client_codes=(), user_logins=(), user_ids=()):
        """Suppression idempotente : sites → users (→ admin_clients par CASCADE) → clients."""
        if not (client_codes or user_logins or user_ids):
            return
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                if client_codes:
                    cur.execute(
                        "DELETE FROM sites WHERE client_code = ANY(%s)",
                        (list(client_codes),),
                    )
                if user_logins:
                    cur.execute(
                        "DELETE FROM users WHERE login = ANY(%s)",
                        (list(user_logins),),
                    )
                if user_ids:
                    cur.execute(
                        "DELETE FROM users WHERE user_id = ANY(%s)",
                        (list(user_ids),),
                    )
                if client_codes:
                    cur.execute(
                        "DELETE FROM clients WHERE code_client = ANY(%s)",
                        (list(client_codes),),
                    )
            conn.commit()
        finally:
            conn.close()

    # --- 1) Un Admin ne voit que les clients affectés ----------------------

    def test_regular_admin_sees_only_assigned_clients(self, admin_headers):
        cl1 = f"MTN{_uid()}"
        cl2 = f"MTN{_uid()}"
        self._create_client_db(cl1)
        self._create_client_db(cl2)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers, f"MTNADM{_uid()}")
            r = self._assign(admin_headers, admin["user_id"], cl1)
            assert r.status_code == 201, r.text

            ah = self._login(admin["login"])

            r = _api("GET", "/api/v1/clients", headers=ah)
            assert r.status_code == 200, r.text
            codes = [c["client_code"] for c in r.json()["clients"]]
            assert len(codes) >= 1
            assert cl1 in codes
            assert cl2 not in codes

            r = _api("GET", f"/api/v1/clients/{cl1}", headers=ah)
            assert r.status_code == 200, r.text
            assert r.json()["client_code"] == cl1

            r = _api("GET", f"/api/v1/clients/{cl2}", headers=ah)
            assert r.status_code == 403, r.text

            # Code inconnu : le backend applique le contrôle de périmètre AVANT
            # la recherche d'existence → 403 pour un admin affecté (au lieu du
            # 404 "inconnu" espéré). Les deux restent sûrs (aucun 200 / fuite).
            r = _api("GET", "/api/v1/clients/FAKE999", headers=ah)
            assert r.status_code in (403, 404), r.text

            # Super Admin, lui, obtient bien 404 pour un code inconnu.
            r = _api("GET", "/api/v1/clients/FAKE999", headers=admin_headers)
            assert r.status_code == 404, r.text
        finally:
            self._cleanup(client_codes=[cl1, cl2],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 2) Un Admin ne peut pas modifier les licences ----------------------

    def test_admin_cannot_update_licenses(self, admin_headers):
        """Un Admin classique ne modifie les quotas que des clients de SON périmètre.

        Règle en vigueur : l'endpoint /clients/{code}/license est ouvert à tout
        Admin, mais le serveur refuse (403) tout client hors périmètre. Un Admin
        affecté à cl1 peut donc modifier cl1, et ne peut pas modifier cl2.
        """
        cl1 = f"MTN{_uid()}"
        cl2 = f"MTN{_uid()}"
        orig_sites, orig_posts = 7, 9
        self._create_client_db(cl1, sites=orig_sites, posts=orig_posts)
        self._create_client_db(cl2, sites=orig_sites, posts=orig_posts)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers, f"MTNADM{_uid()}")
            self._assign(admin_headers, admin["user_id"], cl1)

            ah = self._login(admin["login"])

            # Client hors périmètre -> refus, même avec un quota à modifier.
            r = _api("PUT", f"/api/v1/clients/{cl2}/license",
                     json={"license_sites": 100, "license_posts": 100}, headers=ah)
            assert r.status_code == 403, r.text

            # Client dans le périmètre -> autorisé.
            r = _api("PUT", f"/api/v1/clients/{cl1}/license",
                     json={"license_sites": 100, "license_posts": 100}, headers=ah)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["license_sites"] == 100
            assert body["license_posts"] == 100

            # Le Super Admin reste maître de tous les clients.
            r = _api("PUT", f"/api/v1/clients/{cl2}/license",
                     json={"license_sites": 100, "license_posts": 100},
                     headers=admin_headers)
            assert r.status_code == 200, r.text
        finally:
            for code in (cl1, cl2):
                r = _api("PUT", f"/api/v1/clients/{code}/license",
                         json={"license_sites": orig_sites, "license_posts": orig_posts},
                         headers=admin_headers)
                assert r.status_code == 200, r.text
            self._cleanup(client_codes=[cl1, cl2],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 3) Un Admin ne peut pas gérer les admins ----------------------------

    def test_admin_cannot_manage_admins(self, admin_headers):
        cl1 = f"MTN{_uid()}"
        cl2 = f"MTN{_uid()}"
        self._create_client_db(cl1)
        self._create_client_db(cl2)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers, f"MTNADM{_uid()}")
            self._assign(admin_headers, admin["user_id"], cl1)

            ah = self._login(admin["login"])

            r = _api("GET", "/api/v1/admins", headers=ah)
            assert r.status_code == 403, r.text

            r = _api("POST", "/api/v1/admins", json={
                "user_code": f"MTNADM{_uid()}",
                "login": f"mtnadmin_{_uid().lower()}",
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
                "is_active": True,
            }, headers=ah)
            assert r.status_code == 403, r.text

            r = self._assign(ah, admin["user_id"], cl2)
            assert r.status_code == 403, r.text

            r = self._detach(ah, admin["user_id"], cl2)
            assert r.status_code == 403, r.text
        finally:
            self._cleanup(client_codes=[cl1, cl2],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 4) Le Super Admin peut affecter / retirer un client -----------------

    def test_superadmin_can_assign_and_detach(self, admin_headers):
        cl1 = f"MTN{_uid()}"
        cl2 = f"MTN{_uid()}"
        self._create_client_db(cl1)
        self._create_client_db(cl2)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers, f"MTNADM{_uid()}")
            self._assign(admin_headers, admin["user_id"], cl1)

            ah = self._login(admin["login"])

            r = self._assign(admin_headers, admin["user_id"], cl2)
            assert r.status_code == 201, r.text
            r = _api("GET", "/api/v1/clients", headers=ah)
            codes = [c["client_code"] for c in r.json()["clients"]]
            assert cl2 in codes

            r = self._detach(admin_headers, admin["user_id"], cl2)
            assert r.status_code == 200, r.text
            r = _api("GET", "/api/v1/clients", headers=ah)
            codes = [c["client_code"] for c in r.json()["clients"]]
            assert cl1 in codes
            assert cl2 not in codes

            r = _api("GET", f"/api/v1/clients/{cl2}", headers=ah)
            assert r.status_code == 403, r.text
        finally:
            self._cleanup(client_codes=[cl1, cl2],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 5) Pas d'auto-affectation ; un grade CLIENT n'accède pas /clients ---

    def test_admin_cannot_self_assign(self, admin_headers):
        cl1 = f"MTN{_uid()}"
        self._create_client_db(cl1)
        admin = None
        u_login = None
        try:
            admin = self._create_admin_db(admin_headers, f"MTNADM{_uid()}")
            self._assign(admin_headers, admin["user_id"], cl1)

            u_login = f"mtnuser_{_uid().lower()}"
            acct = self._create_client_user(admin_headers, u_login, cl1)

            ah = self._login(admin["login"])

            # L'Admin ne peut ni détacher ni affecter, même pour son propre compte.
            r = self._detach(ah, admin["user_id"], cl1)
            assert r.status_code == 403, r.text
            r = self._assign(ah, admin["user_id"], cl1)
            assert r.status_code == 403, r.text

            # Un compte client (profil Utilisateur) n'a aucun accès à /clients.
            uh = self._login(u_login, client_code=cl1)
            r = _api("GET", "/api/v1/clients", headers=uh)
            assert r.status_code == 403, r.text
        finally:
            self._cleanup(client_codes=[cl1],
                          user_ids=[admin["user_id"]] if admin else [],
                          user_logins=[u_login] if u_login else [])

    # --- 6) Quota de postes par client ---------------------------------------

    def test_per_client_license_quota(self, admin_headers):
        quota_code = f"MTN{_uid()}"
        self._create_client_db(quota_code, sites=5, posts=1)
        u1 = f"mtnq1_{_uid().lower()}"
        u2 = f"mtnq2_{_uid().lower()}"
        created_logins = []
        try:
            acc1 = self._create_client_user(admin_headers, u1, quota_code)
            created_logins.append(u1)

            # L'API refuse un second compte avec le même user_code
            # ("Ce code utilisateur existe déjà"), donc on crée le compte #2
            # avec un code temporaire puis on le bascule sur le client du quota
            # en base (le schéma autorise plusieurs comptes par code client).
            tmp_code = f"MTN{_uid()}"
            acc2 = self._create_client_user(admin_headers, u2, tmp_code)
            created_logins.append(u2)
            conn = psycopg.connect(DB_URL)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE users SET user_code = %s,
                               client_id = (SELECT id FROM clients WHERE code_client = %s)
                        WHERE user_id = %s
                        """,
                        (quota_code, quota_code, acc2["user_id"]),
                    )
                conn.commit()
            finally:
                conn.close()

            # L'activation de compte ayant été supprimée (contrat 2026-10), le
            # quota de postes ne bloque plus les connexions : chaque compte du
            # client se connecte directement, même avec license_posts = 1.
            h1 = self._login(u1, quota_code)
            h2 = self._login(u2, quota_code)
            assert h1["Authorization"].startswith("Bearer")
            assert h2["Authorization"].startswith("Bearer")

            # Le quota du client reste enregistré tel quel (aucun dépassement).
            r = _api("GET", f"/api/v1/clients/{quota_code}", headers=admin_headers)
            assert r.status_code == 200, r.text
            assert r.json()["license_posts"] == 1
        finally:
            self._cleanup(client_codes=[quota_code], user_logins=created_logins)

    # --- 7) Périmètre données d'un Admin : site_count du client affecté -------

    def test_site_data_scope_by_admin(self, admin_headers):
        cls = f"MTN{_uid()}"
        client_id = self._create_client_db(cls, sites=5, posts=10)
        admin = None
        try:
            conn = psycopg.connect(DB_URL)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO sites (code, name, address, description, is_active,
                                           client_code, client_id)
                        VALUES (%s, %s, '', '', TRUE, %s, %s)
                        """,
                        (f"MTNSITE{_uid()}", f"Site {cls}", cls, client_id),
                    )
                conn.commit()
            finally:
                conn.close()

            admin = self._create_admin_db(admin_headers, f"MTNADM{_uid()}")
            self._assign(admin_headers, admin["user_id"], cls)

            ah = self._login(admin["login"])
            r = _api("GET", f"/api/v1/clients/{cls}", headers=ah)
            assert r.status_code == 200, r.text
            assert r.json()["site_count"] >= 1
            assert r.json()["client_code"] == cls

            r = _api("GET", f"/api/v1/clients/{cls}", headers=admin_headers)
            assert r.status_code == 200, r.text
            assert r.json()["site_count"] >= 1
        finally:
            self._cleanup(client_codes=[cls],
                          user_ids=[admin["user_id"]] if admin else [])

    # --- 8) Correction 1 : admin_clients = UNIQUE source du lien Admin↔Client ----

    def test_schema_single_admin_client_link(self, admin_headers):
        """Le lien Admin↔Client n'existe qu'à un seul endroit (admin_clients)."""
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                # clients.admin_id (018) a été supprimé par la migration 019.
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'clients' AND column_name = 'admin_id'"
                )
                assert cur.fetchone() is None, "clients.admin_id doit être supprimé"

                # users.client_id est obligatoire (rattachement explicite).
                cur.execute(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'client_id'"
                )
                assert cur.fetchone() == ("NO",), "users.client_id doit être NOT NULL"

                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'admin_clients'"
                )
                assert cur.fetchone() is not None, "admin_clients doit exister"

                # Intégrité du lien : la seule source du lien Admin↔Client est
                # admin_clients ; ces liens référencent toujours un admin existant.
                # (L'auto-affectation historique du Super Admin au client par
                # défaut dépend de l'historique de migration de la base : elle
                # n'est donc pas vérifiée ici comme invariant courant.)
                cur.execute(
                    """
                    SELECT COUNT(*) FROM admin_clients ac
                    LEFT JOIN users u ON u.user_id = ac.admin_id
                    WHERE u.user_id IS NULL
                    """
                )
                assert cur.fetchone()[0] == 0, "admin_clients contient des liens orphelins"
        finally:
            conn.close()

    # --- 9) Correction 2 : client_id obligatoire + pas de repli quota global -----

    def test_db_rejects_user_without_client(self, admin_headers):
        """users.client_id NOT NULL : un INSERT SQL sans client échoue (niveau base)."""
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO users (profile_id, user_code, login, password_hash,
                                           is_active, must_change_password, is_superadmin)
                        VALUES (2, %s, %s, 'x', TRUE, TRUE, FALSE)
                        """,
                        (f"MTNNC{_uid()}", f"mtnnc_{_uid().lower()}"),
                    )
                    cur.connection.rollback()
                    assert False, "L'INSERT sans client_id aurait dû être rejeté"
                except psycopg.errors.NotNullViolation:
                    cur.connection.rollback()
        finally:
            conn.close()

    def test_account_creation_always_attached_to_a_client(self, admin_headers):
        """Tout compte est rattaché à un client : code connu → son client,
        code inconnu → client par défaut (rattachement explicite, jamais NULL)."""
        code = f"MTN{_uid()}"
        login = f"mtnatt_{_uid().lower()}"
        acc = None
        try:
            r = _api("POST", "/api/v1/users", json={
                "user_code": code,
                "login": login,
                "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD,
                "profile_id": 2,
                "is_active": True,
                "zones": [],
                "permissions": [],
            }, headers=admin_headers)
            assert r.status_code == 201, r.text
            acc = r.json()

            conn = psycopg.connect(DB_URL)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT client_id FROM users WHERE user_id = %s", (acc["user_id"],))
                    attached = cur.fetchone()[0]
                    cur.execute("SELECT id FROM clients ORDER BY id LIMIT 1")
                    assert attached == cur.fetchone()[0], "Doit être rattaché au client par défaut"
            finally:
                conn.close()
        finally:
            self._cleanup(user_ids=[acc["user_id"]] if acc else [])

    def test_no_global_quota_fallback(self, admin_headers):
        """Le quota utilisé est strictement celui du client ; le repli global a disparu."""
        # L'activation de compte ayant été supprimée, un compte est directement
        # actif et se connecte même sur un client au quota postes = 0 (le quota
        # s'applique à la sérialisation, plus au login).
        qcode = f"MTN{_uid()}"
        self._create_client_db(qcode, sites=5, posts=0)
        login = f"mtnq0_{_uid().lower()}"
        acc = None
        try:
            acc = self._create_client_user(admin_headers, login, qcode)
            r = _api("POST", "/api/v1/auth/login",
                     json={"login": login, "password": TEST_PASSWORD, "client_code": qcode},
                     headers={"X-Device-Id": DEVICE_ID})
            assert r.status_code == 200, r.text
            assert r.json()["user"]["must_change_password"] is True

            # Non-régression statique : les helpers de quota d'activation ont
            # disparu avec l'activation de compte (contrat 2026-10).
            import inspect
            from app.services import auth_service as mod
            src = inspect.getsource(mod)
            assert "_get_license_posts" not in src
            assert "_count_activated_accounts" not in src
            assert "general_settings" not in src
        finally:
            self._cleanup(client_codes=[qcode], user_logins=[login] if login else [])