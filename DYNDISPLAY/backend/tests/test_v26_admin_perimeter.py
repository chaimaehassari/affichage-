import uuid
import pytest
import requests

from tests.conftest import BASE_URL, ADMIN_LOGIN, ADMIN_PASSWORD, TEST_DEVICE, login_as, make_headers

_SITE_PERMS = [
    {"permission_id": 14, "can_view": True},
    {"permission_id": 15, "can_create": True, "can_view": True},
    {"permission_id": 16, "can_update": True, "can_view": True},
    {"permission_id": 17, "can_delete": True, "can_view": True},
    {"permission_id": 18, "can_create": True, "can_view": True},
    {"permission_id": 19, "can_update": True, "can_view": True},
    {"permission_id": 20, "can_delete": True, "can_view": True},
]
_ADMIN_PERMS = _SITE_PERMS + [
    {"permission_id": 11, "can_view": True, "can_create": True, "can_update": True, "can_delete": True},
]
_TEST_PWD = "Test@1234"


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


@pytest.mark.v26
class TestAdminPerimeter:
    def _create_admin(self, admin_token, client_codes):
        code = f"A26{_uid()}"
        login = f"adm26_{_uid()}"
        payload = {
            "user_code": code,
            "login": login,
            "password": _TEST_PWD,
            "password_confirm": _TEST_PWD,
            "profile_id": 1,
            "is_active": True,
            "zones": [],
            "permissions": _ADMIN_PERMS,
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=make_headers(admin_token))
        assert r.status_code == 201, r.text
        body = r.json()

        # Affectation des clients via PUT /admins (réservé au Super Admin).
        # Sans cette étape l'admin n'a aucun périmètre et ne voit rien :
        # `admin_clients` est la seule source du scope d'un Admin classique.
        if client_codes:
            upd = _api("PUT", f"/api/v1/admins/{body['user_id']}",
                       json={"login": login, "is_active": True,
                             "client_codes": list(client_codes)},
                       headers=make_headers(admin_token))
            assert upd.status_code == 200, f"affectation client impossible: {upd.text}"

        return {"user_code": code, "login": login, "user_id": body.get("user_id")}

    def _create_client_user(self, admin_token, code):
        """Crée un client en base (aucun endpoint de création n'existe)."""
        import psycopg
        from tests._test_config import get_test_db_url
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

    def _login_admin(self, admin):
        r = _api("POST", "/api/v1/auth/login",
                 json={"login": admin["login"], "password": _TEST_PWD},
                 headers={"X-Device-Id": TEST_DEVICE})
        assert r.status_code == 200, f"login admin echoue: {r.status_code} {r.text}"
        return r.json()["access_token"]

    def test_settings_forbidden_regular_admin(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        assert token
        self._create_client_user(token, f"C26L{_uid()}")
        admin = self._create_admin(token, [])
        h = make_headers(self._login_admin(admin))
        assert _api("GET", "/api/v1/settings", headers=h).status_code == 403
        assert _api("GET", "/api/v1/ftp-profiles", headers=h).status_code == 403
        assert _api("POST", "/api/v1/settings/test-ftp", json={"host": "h"}, headers=h).status_code == 403
        # verify-access n'est plus réservé au Super Admin : chaque Administrateur
        # déverrouille les Paramètres avec SON mot de passe de connexion. Un
        # mauvais mot de passe est donc un 401 (échec métier), pas un 403.
        # Les onglets superadmin-only ci-dessus restent bien protégés.
        assert _api("POST", "/api/v1/settings/verify-access", json={"password": "x"}, headers=h).status_code == 401
        # La licence est désormais gérée par client (PUT /clients/{code}/license) :
        # hors périmètre, elle est refusée.
        assert _api("PUT", "/api/v1/clients/C26Lxxxx/license",
                    json={"license_sites": 5, "license_posts": 5}, headers=h).status_code in (403, 404)
        assert _api("POST", "/api/v1/settings/regenerate-client-code", headers=h).status_code == 403
        # Le verrouillage de session reste lisible par tout Administrateur.
        assert _api("GET", "/api/v1/settings/session-timeout", headers=h).status_code == 200

    def test_session_timeout_readable_by_any_authenticated_user(self):
        """SessionLock est monte sur TOUTES les routes protegees.

        Le réglage est une simple durée d'inactivité : le 403 pour un compte
        client ou un utilisateur simple cassait silencieusement leur
        verrouillage de session, en plus du bruit dans la console.
        """
        admin = self._create_admin(login_as(ADMIN_LOGIN, ADMIN_PASSWORD), [])
        h = make_headers(self._login_admin(admin))
        body = _api("GET", "/api/v1/settings/session-timeout", headers=h).json()
        assert "session_timeout_minutes" in body

        # Sans jeton : 401. Jamais la donnée.
        assert _api("GET", "/api/v1/settings/session-timeout").status_code == 401

    def test_admins_crud_forbidden_regular_admin(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        admin = self._create_admin(token, [])
        h = make_headers(self._login_admin(admin))
        assert _api("GET", "/api/v1/admins", headers=h).status_code == 403
        assert _api("POST", "/api/v1/admins", json={"login": "x", "password": "Test@1234",
                                                    "password_confirm": "Test@1234", "profile_id": 1},
                    headers=h).status_code == 403

    def test_client_license_scoped_to_own_clients(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        mine = f"C26M{_uid()}"
        other = f"C26O{_uid()}"
        self._create_client_user(token, mine)
        self._create_client_user(token, other)
        admin = self._create_admin(token, [mine])
        h = make_headers(self._login_admin(admin))

        listed = _api("GET", "/api/v1/clients", headers=h)
        assert listed.status_code == 200, listed.text
        codes = [c["client_code"] for c in listed.json().get("clients", [])]
        assert mine in codes, f"client propre absent: {codes}"
        assert other not in codes, f"fuite d'un client tiers: {codes}"

        ok = _api("PUT", f"/api/v1/clients/{mine}/license",
                  json={"license_sites": 4, "license_posts": 9}, headers=h)
        assert ok.status_code == 200, ok.text

        denied = _api("PUT", f"/api/v1/clients/{other}/license",
                      json={"license_sites": 999, "license_posts": 999}, headers=h)
        assert denied.status_code in (403, 404), f"licence tierce acceptee: {denied.status_code} {denied.text}"

        # La tentative|IDOR ne doit avoir modifié aucun quota.
        still = _api("PUT", f"/api/v1/clients/{other}/license",
                     json={"license_sites": 1, "license_posts": 1}, headers=h)
        assert still.status_code in (403, 404), still.text

    def test_device_endpoints_removed(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        admin = self._create_admin(token, [])
        h = make_headers(self._login_admin(admin))

        # Le verrou d'appareil ayant ete supprime (contrat 2026-10), les
        # endpoints de listing / revoke d'appareils n'existent plus (404/405).
        r = _api("GET", "/api/v1/settings/accounts/devices", headers=h)
        assert r.status_code in (404, 405), r.text
        r = _api("POST", f"/api/v1/settings/accounts/1/revoke-device", headers=h)
        assert r.status_code in (404, 405), r.text

    def test_change_password_requires_current_password(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        admin = self._create_admin(token, [])
        h = make_headers(self._login_admin(admin))

        # Mauvais mot de passe actuel -> refus, et le compte reste utilisable.
        bad = _api("POST", "/api/v1/settings/change-password",
                   json={"current_password": "Wrong@999", "new_password": "Other@1234"}, headers=h)
        assert bad.status_code in (400, 401, 422), f"ancien mot de passe non verifie: {bad.status_code} {bad.text}"
        relogin = _api("POST", "/api/v1/auth/login",
                       json={"login": admin["login"], "password": _TEST_PWD},
                       headers={"X-Device-Id": TEST_DEVICE})
        assert relogin.status_code == 200, f"session invalidee a tort: {relogin.status_code} {relogin.text}"

        new_pwd = f"Nw{_uid()}@Aa"
        good = _api("POST", "/api/v1/settings/change-password",
                    json={"current_password": _TEST_PWD, "new_password": new_pwd}, headers=h)
        assert good.status_code == 200, good.text
        after = _api("POST", "/api/v1/auth/login",
                     json={"login": admin["login"], "password": new_pwd},
                     headers={"X-Device-Id": TEST_DEVICE})
        assert after.status_code == 200, f"nouveau mot de passe rejete: {after.status_code} {after.text}"

    def test_empty_scope_admin_sees_nothing(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        client_code = f"C26Z{_uid()}"
        self._create_client_user(token, client_code)
        admin = self._create_admin(token, [])
        h = make_headers(self._login_admin(admin))

        groups = _api("GET", "/api/v1/groups", headers=h)
        assert groups.status_code == 200, groups.text
        # GET /groups a `response_model=list[GroupOut]` : le corps est une liste.
        assert groups.json() == [], "groupes visibles sans perimetre"

        clients = _api("GET", "/api/v1/clients", headers=h)
        assert clients.status_code == 200, clients.text
        assert clients.json().get("clients", []) == [], "clients visibles sans perimetre"


@pytest.mark.v26
class TestAdminUsersPerimeter:
    """Admin A ne doit voir et gérer QUE ses propres utilisateurs."""

    def _create_admin_with_clients(self, admin_token, client_codes):
        code = f"A27{_uid()}"
        login = f"adm27_{_uid()}"
        payload = {
            "user_code": code,
            "login": login,
            "password": _TEST_PWD,
            "password_confirm": _TEST_PWD,
            "profile_id": 1,
            "is_active": True,
            "zones": [],
            "permissions": _ADMIN_PERMS,
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=make_headers(admin_token))
        assert r.status_code == 201, r.text
        body = r.json()

        # Affectation des clients via PUT /admins (réservé au Super Admin).
        # AdminUpdateRequest exige `login` et `is_active` : le PUT est un
        # remplacement complet, pas un patch.
        if client_codes:
            upd = _api("PUT", f"/api/v1/admins/{body['user_id']}",
                       json={"login": login, "is_active": True,
                             "client_codes": list(client_codes)},
                       headers=make_headers(admin_token))
            assert upd.status_code == 200, f"affectation client impossible: {upd.text}"

        tok = _api("POST", "/api/v1/auth/login",
                   json={"login": login, "password": _TEST_PWD},
                   headers={"X-Device-Id": TEST_DEVICE})
        assert tok.status_code == 200, f"login admin: {tok.status_code} {tok.text}"
        return {"user_id": body["user_id"], "login": login,
                "token": tok.json()["access_token"], "clients": list(client_codes)}

    @staticmethod
    def _create_client(admin_token, code):
        import psycopg
        from tests._test_config import get_test_db_url
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

    def _create_user_payload(self, login, client_code):
        return {
            "user_code": client_code,
            "login": login,
            "password": _TEST_PWD,
            "password_confirm": _TEST_PWD,
            "profile_id": 3,
            "is_active": True,
            "zones": [],
            "permissions": _SITE_PERMS,
        }

    def test_admin_sees_own_users_only(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code_a, code_b = f"C27A{_uid()}", f"C27B{_uid()}"
        self._create_client(token, code_a)
        self._create_client(token, code_b)
        admin_a = self._create_admin_with_clients(token, [code_a])
        admin_b = self._create_admin_with_clients(token, [code_b])
        ha = make_headers(admin_a["token"])
        hb = make_headers(admin_b["token"])

        # Admin A cree un compte sur SON client.
        login_ua = f"usr27a_{_uid()}"
        created = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(login_ua, code_a), headers=ha)
        assert created.status_code == 201, f"creation refusee: {created.status_code} {created.text}"
        uid_a = created.json()["user_id"]

        # Il apparait immediatement chez Admin A, cote client et sans rechargement.
        listed_a = _api("GET", "/api/v1/users", headers=ha)
        assert listed_a.status_code == 200, listed_a.text
        ids_a = [u["user_id"] for u in listed_a.json().get("users", [])]
        assert uid_a in ids_a, "compte cree absent de la liste de Admin A"
        codes_a = [u.get("client_name") for u in listed_a.json().get("users", [])]
        assert any(code_a in str(c) for c in codes_a), f"client propre absent: {codes_a}"

        # Admin A refresh de nouveau : la donnee est bien persistee.
        again = _api("GET", "/api/v1/users", headers=ha)
        assert uid_a in [u["user_id"] for u in again.json().get("users", [])]

        # Admin B ne voit ni le compte ni le client d\Admin A.
        listed_b = _api("GET", "/api/v1/users", headers=hb)
        assert listed_b.status_code == 200, listed_b.text
        ids_b = [u["user_id"] for u in listed_b.json().get("users", [])]
        assert uid_a not in ids_b, "compte d'Admin A visible par Admin B"
        clients_b = [c["client_code"] for c in
                     _api("GET", "/api/v1/clients", headers=hb).json().get("clients", [])]
        assert code_a not in clients_b, f"client d'Admin A visible par Admin B: {clients_b}"

    def test_admin_cannot_touch_other_admin_user(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code_a, code_b = f"C27C{_uid()}", f"C27D{_uid()}"
        self._create_client(token, code_a)
        self._create_client(token, code_b)
        admin_a = self._create_admin_with_clients(token, [code_a])
        admin_b = self._create_admin_with_clients(token, [code_b])
        ha = make_headers(admin_a["token"])
        hb = make_headers(admin_b["token"])

        created = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27b_{_uid()}", code_a), headers=ha)
        assert created.status_code == 201, created.text
        uid = created.json()["user_id"]

        assert _api("GET", f"/api/v1/users/{uid}", headers=hb).status_code in (403, 404)
        assert _api("PUT", f"/api/v1/users/{uid}",
                    json={"login": "pirate", "profile_id": 3}, headers=hb).status_code in (403, 404)
        assert _api("DELETE", f"/api/v1/users/{uid}", headers=hb).status_code in (403, 404)

        # Le compte est intact.
        still = _api("GET", f"/api/v1/users/{uid}", headers=ha)
        assert still.status_code == 200, still.text
        assert still.json().get("login") != "pirate", "compte modifie par un tiers"

    def test_admin_creates_only_on_own_clients(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code_a, code_b = f"C27E{_uid()}", f"C27F{_uid()}"
        self._create_client(token, code_a)
        self._create_client(token, code_b)
        admin_a = self._create_admin_with_clients(token, [code_a])
        ha = make_headers(admin_a["token"])

        # Code client d'un autre admin -> refus explicite.
        denied = _api("POST", "/api/v1/users",
                      json=self._create_user_payload(f"usr27x_{_uid()}", code_b), headers=ha)
        assert denied.status_code == 400, f"client tiers accepte: {denied.status_code} {denied.text}"

        # Code client inconnu -> refus explicite (avant: repli silencieux sur le
        # client par defaut, qui n'est dans aucun perimetre d'admin).
        unknown = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27y_{_uid()}", f"NOPE{_uid()}"), headers=ha)
        assert unknown.status_code == 400, f"code inconnu accepte: {unknown.status_code} {unknown.text}"

    def test_admin_without_clients_cannot_create_user(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C27G{_uid()}"
        self._create_client(token, code)
        admin = self._create_admin_with_clients(token, [])
        h = make_headers(admin["token"])

        refused = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27z_{_uid()}", code), headers=h)
        assert refused.status_code == 400, f"creation sans perimetre acceptee: {refused.status_code}"

        listed = _api("GET", "/api/v1/users", headers=h)
        assert listed.status_code == 200, listed.text
        assert listed.json().get("users", []) == [], "liste non vide sans perimetre"

    def test_admin_can_update_and_delete_own_user(self):
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C27H{_uid()}"
        self._create_client(token, code)
        admin = self._create_admin_with_clients(token, [code])
        h = make_headers(admin["token"])

        created = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27m_{_uid()}", code), headers=h)
        assert created.status_code == 201, created.text
        uid = created.json()["user_id"]

        upd = _api("PUT", f"/api/v1/users/{uid}",
                   json={"login": f"usr27m2_{_uid()}", "profile_id": 3}, headers=h)
        assert upd.status_code == 200, f"edition refusee: {upd.status_code} {upd.text}"

        dele = _api("DELETE", f"/api/v1/users/{uid}", headers=h)
        assert dele.status_code == 200, f"suppression refusee: {dele.status_code} {dele.text}"
        assert _api("GET", f"/api/v1/users/{uid}", headers=h).status_code in (403, 404)

    # --- Liste des utilisateurs : « crees par moi OU affectes a moi » ---

    def test_shared_client_admin_sees_only_users_he_created(self):
        """Un client affecte a plusieurs admins ne doit pas afficher tous
        ses comptes a chacun d'eux : chacun ne voit que ceux qu'il a crees."""
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C27I{_uid()}"
        self._create_client(token, code)
        admin_a = self._create_admin_with_clients(token, [code])
        admin_b = self._create_admin_with_clients(token, [code])
        ha = make_headers(admin_a["token"])
        hb = make_headers(admin_b["token"])

        created = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27s_{_uid()}", code), headers=ha)
        assert created.status_code == 201, created.text
        uid = created.json()["user_id"]

        ids_a = [u["user_id"] for u in _api("GET", "/api/v1/users", headers=ha).json()["users"]]
        ids_b = [u["user_id"] for u in _api("GET", "/api/v1/users", headers=hb).json()["users"]]
        assert uid in ids_a, "compte cree absent de la liste de son auteur"
        assert uid not in ids_b, "compte d'Admin A visible par Admin B sur un client partage"

        # Le Super Admin conserve la vue globale.
        hs = make_headers(token)
        ids_s = [u["user_id"] for u in _api("GET", "/api/v1/users", headers=hs).json()["users"]]
        assert uid in ids_s, "compte invisible du Super Admin"

    def test_exclusive_client_admin_sees_unassigned_users(self):
        """Les comptes sans admin_id d'un client qui lui est propre restent
        visibles : ils ont ete herites, pas crees par un autre admin."""
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C27J{_uid()}"
        self._create_client(token, code)
        admin = self._create_admin_with_clients(token, [code])
        h = make_headers(admin["token"])

        # Cree par le Super Admin : aucun admin_id, compte « herite ».
        created = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27h_{_uid()}", code),
                       headers=make_headers(token))
        assert created.status_code == 201, created.text
        uid = created.json()["user_id"]

        ids = [u["user_id"] for u in _api("GET", "/api/v1/users", headers=h).json()["users"]]
        assert uid in ids, "compte sans admin_id d'un client exclusif invisible"

    def test_shared_client_admin_does_not_see_unassigned_users(self):
        """Un compte sans admin_id sur un client PARTAGE n'appartient a aucun
        admin : seul le Super Admin doit le voir."""
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C27K{_uid()}"
        self._create_client(token, code)
        admin_a = self._create_admin_with_clients(token, [code])
        admin_b = self._create_admin_with_clients(token, [code])

        created = _api("POST", "/api/v1/users",
                       json=self._create_user_payload(f"usr27o_{_uid()}", code),
                       headers=make_headers(token))
        assert created.status_code == 201, created.text
        uid = created.json()["user_id"]

        for admin in (admin_a, admin_b):
            ids = [u["user_id"] for u in
                   _api("GET", "/api/v1/users", headers=make_headers(admin["token"])).json()["users"]]
            assert uid not in ids, f"compte sans proprietaire visible par {admin['login']}"

    def test_shared_client_direct_id_access_denied_cross_admin(self):
        """Exemple de la specification, sur un client PARTAGE.

        Admin A cree User 1 et User 2, Admin B cree User 3 et User 4, les deux
        admins etant affectes au MEME client. Regle exigee :

            Admin A -> {User 1, User 2}
            Admin B -> {User 3, User 4}
            Super Admin -> les quatre

        Le cas_shared_client est le plus expose : les deux admins partagent le
        meme code client, donc un controle base sur le simple rattachement client
        laisse passer n'importe quel ID du client. C'est `users.admin_id` qui
        doit faire foi, aussi bien sur la liste que sur l'acces direct par ID
        (GET / PUT / DELETE / reinitialisation).
        """
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        code = f"C27L{_uid()}"
        self._create_client(token, code)
        admin_a = self._create_admin_with_clients(token, [code])
        admin_b = self._create_admin_with_clients(token, [code])
        ha = make_headers(admin_a["token"])
        hb = make_headers(admin_b["token"])

        own_a, own_b = [], []
        for i in (1, 2):
            r = _api("POST", "/api/v1/users",
                     json=self._create_user_payload(f"usr27a{i}_{_uid()}", code), headers=ha)
            assert r.status_code == 201, r.text
            uid = r.json()["user_id"]
            detail = _api("GET", f"/api/v1/users/{uid}", headers=ha)
            assert detail.status_code == 200, detail.text
            assert detail.json().get("admin_id") == admin_a["user_id"], \
                "la creation n'a pas enregistre l'Admin connecte comme proprietaire"
            own_a.append(uid)
        for i in (3, 4):
            r = _api("POST", "/api/v1/users",
                     json=self._create_user_payload(f"usr27b{i}_{_uid()}", code), headers=hb)
            assert r.status_code == 201, r.text
            uid = r.json()["user_id"]
            detail = _api("GET", f"/api/v1/users/{uid}", headers=hb)
            assert detail.status_code == 200, detail.text
            assert detail.json().get("admin_id") == admin_b["user_id"], \
                "la creation n'a pas enregistre l'Admin connecte comme proprietaire"
            own_b.append(uid)

        # 1. Chaque admin ne voit QUE ses comptes, sur un client partage.
        ids_a = [u["user_id"] for u in _api("GET", "/api/v1/users", headers=ha).json()["users"]]
        ids_b = [u["user_id"] for u in _api("GET", "/api/v1/users", headers=hb).json()["users"]]
        assert set(ids_a) & set(own_a) == set(own_a), "Admin A ne voit pas tous ses comptes"
        assert not (set(ids_a) & set(own_b)), "Admin A voit un compte d'Admin B"
        assert set(ids_b) & set(own_b) == set(own_b), "Admin B ne voit pas tous ses comptes"
        assert not (set(ids_b) & set(own_a)), "Admin B voit un compte d'Admin A"

        # 2. Le Super Admin conserve la vue globale.
        ids_s = [u["user_id"] for u in
                 _api("GET", "/api/v1/users", headers=make_headers(token)).json()["users"]]
        for uid in (*own_a, *own_b):
            assert uid in ids_s, "compte invisible du Super Admin"

        # 3. Acces direct par l'ID d'un compte d'un autre admin : refuse partout.
        foreign = own_b[0]
        for label, resp in (
            ("GET", _api("GET", f"/api/v1/users/{foreign}", headers=ha)),
            ("PUT", _api("PUT", f"/api/v1/users/{foreign}",
                        json={"login": "pirate", "profile_id": 3}, headers=ha)),
            ("DELETE", _api("DELETE", f"/api/v1/users/{foreign}", headers=ha)),
            ("reset-password", _api("POST", f"/api/v1/users/{foreign}/reset-password",
                                    json={"new_password": "Hacked@1234",
                                          "password_confirm": "Hacked@1234"}, headers=ha)),
        ):
            assert resp.status_code in (403, 404), \
                f"{label} sur un compte d'un autre Admin accepte ({resp.status_code})"

        # Le compte est intact et l'autre admin y a toujours acces.
        still = _api("GET", f"/api/v1/users/{foreign}", headers=hb)
        assert still.status_code == 200, still.text
        assert still.json().get("login") != "pirate", "compte modifie par un autre Admin"

        # 4. Un admin ne peut pas s'attribuer un compte en forcant `admin_id`.
        stolen = own_a[0]
        body = self._create_user_payload("stolen", code)
        body["login"] = _api("GET", f"/api/v1/users/{stolen}", headers=ha).json()["login"]
        body["admin_id"] = admin_b["user_id"]
        r = _api("PUT", f"/api/v1/users/{stolen}", json=body, headers=ha)
        assert r.status_code == 200, r.text
        moved = _api("GET", f"/api/v1/users/{stolen}", headers=hb)
        assert moved.status_code in (403, 404), \
            "Admin B a pu s'attribuer le compte d'Admin A via admin_id"

