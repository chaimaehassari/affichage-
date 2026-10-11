import uuid

import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    # Le verrou d'appareil porte sur la SESSION, pas seulement sur le login
    # (cf. test_v16_09) : toute requete authentifiee doit presenter le
    # `X-Device-Id` du poste qui a ouvert la session. Les tests qui
    # construisaient leurs en-tetes a la main oubliaient souvent cet
    # en-tete ; on l'ajoute donc par defaut, sans jamais ecraser celui
    # que le test fournit (les cas "pas de header" restent testables).
    headers = kwargs.get("headers") or {}
    if "Authorization" in headers:
        kwargs = {**kwargs, "headers": {"X-Device-Id": "pytest-device-0001", **headers}}
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


TEST_PASSWORD = "Test@1234"


SITE_POST_PERMISSIONS = [
    {"permission_id": 14, "can_view": True},   # list_sites_posts
    {"permission_id": 15, "can_create": True, "can_view": True},  # create_site
    {"permission_id": 16, "can_update": True, "can_view": True},  # update_site
    {"permission_id": 17, "can_delete": True, "can_view": True},  # delete_site
    {"permission_id": 18, "can_create": True, "can_view": True},  # create_post
    {"permission_id": 19, "can_update": True, "can_view": True},  # update_post
    {"permission_id": 20, "can_delete": True, "can_view": True},  # delete_post
]

SUPER_PERMISSIONS = SITE_POST_PERMISSIONS + [
    {"permission_id": 12, "can_view": True},   # menu_config (Supervision)
]

# Clients crees par les fixtures de ce fichier (voir _create_client).
_TEMP_CLIENTS: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup_temp_clients():
    """Supprime les clients temporaires et le contenu qui y est rattache.

    Sans ce nettoyage, chaque execution ajoute un client (et ses sites) a la
    table `clients`, qui est partagee avec le reste de la suite.
    """
    yield
    if not _TEMP_CLIENTS:
        return
    import psycopg
    from tests._test_config import get_test_db_url
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id FROM clients c
                WHERE c.code_client = ANY(%s)
                """,
                (_TEMP_CLIENTS,),
            )
            ids = [r[0] for r in cur.fetchall()]
            if ids:
                cur.execute("DELETE FROM posts WHERE site_id IN "
                            "(SELECT site_id FROM sites WHERE client_id = ANY(%s))", (ids,))
                cur.execute("DELETE FROM sites WHERE client_id = ANY(%s)", (ids,))
                cur.execute("DELETE FROM clients WHERE id = ANY(%s)", (ids,))
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.clear()


def _create_client_row(user_code: str) -> str:
    """Cree un vrai client dont le `code_client` est le `user_code` du compte.

    `UserService._resolve_client_id()` rattache un compte a un client en
    cherchant son `user_code` parmi les `clients.code_client` ; sans ce
    preparatory le compte tomberait sur le client par defaut, partage par
    tous les autres comptes de la base. Les tests verifient l'isolation entre
    « clients » : il leur faut donc un client reel et distinct par compte.
    """
    import psycopg
    from tests._test_config import get_test_db_url
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clients (code_client, nom_client, license_sites, license_posts)
                VALUES (%s, %s, 10, 50)
                """,
                (user_code, f"Client {user_code}"),
            )
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.append(user_code)
    return user_code


@pytest.mark.v14
class TestClientScope:

    def _create_client(self, admin_headers, permissions=None):
        user_code = f"SCO{_uid()}"
        _create_client_row(user_code)
        login = f"cliscope_{_uid()}"
        payload = {
            "user_code": user_code,
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "zones": [],
            "permissions": permissions if permissions is not None else SITE_POST_PERMISSIONS,
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
        assert r.status_code == 201, r.text
        return {"user_code": user_code, "login": login}

    def _find_user(self, admin_headers, login):
        users = _api("GET", "/api/v1/users", headers=admin_headers).json().get("users", [])
        for u in users:
            if u["login"] == login:
                return u
        return None

    def _delete_user(self, admin_headers, user_id):
        _api("DELETE", f"/api/v1/users/{user_id}", headers=admin_headers)

    def _login(self, login, user_code):
        r = _api("POST", "/api/v1/auth/login", json={
            "login": login, "password": TEST_PASSWORD, "client_code": user_code,
        }, headers={"X-Device-Id": "pytest-device-0001"})
        assert r.status_code == 200, r.text
        return r.json()

    def _client_headers(self, admin_headers, permissions=None):
        c = self._create_client(admin_headers, permissions=permissions)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        return {"client": c, "user": u, "headers": headers}

    def _create_site(self, admin_headers, code, client_code=None):
        # Regle metier : « un site appartient toujours a un client precis »
        # (SiteService._resolve_client_id). Un site sans `client_code` n'existe
        # donc plus. Les cas `client_code=None` de ces tests voulaient dire
        # « un site qui n'appartient PAS au client observe » : on le rattache a
        # un client tiers jetable, ce qui preserve exactement l'assertion de
        # non-visibilite testee ensuite.
        resolved = client_code or _create_client_row(f"OTH{_uid()}")
        payload = {
            "code": code, "name": f"Site {code}", "address": "",
            "description": "", "is_active": True, "client_code": resolved,
        }
        r = _api("POST", "/api/v1/sites", json=payload, headers=admin_headers)
        assert r.status_code == 201, r.text
        return r.json()

    def _create_post(self, headers, site_id, code):
        r = _api("POST", "/api/v1/posts", json={
            "site_id": site_id, "code": code, "name": f"Poste {code}",
            "player_type": "Windows", "ip_address": "", "is_active": True,
        }, headers=headers)
        assert r.status_code == 201, r.text
        return r.json()

    def _assign_group(self, admin_headers, user_id, groups):
        ud = _api("GET", f"/api/v1/users/{user_id}", headers=admin_headers).json()
        payload = {
            "user_code": ud.get("user_code") or "",
            "login": ud["login"],
            "email": ud.get("email") or "",
            "profile_id": ud["profile_id"],
            "is_active": ud["is_active"],
            "zones": [z["zone_number"] for z in ud.get("zones", []) if z.get("is_allowed")],
            "groups": groups,
            "permissions": [
                {"permission_id": p["permission_id"], "can_view": p["can_view"],
                 "can_create": p["can_create"], "can_update": p["can_update"],
                 "can_delete": p["can_delete"]}
                for p in ud.get("permissions", [])
            ],
        }
        r = _api("PUT", f"/api/v1/users/{user_id}", json=payload, headers=admin_headers)
        assert r.status_code == 200, r.text

    # SCO-01: l'admin voit tous les sites ; chaque client ne voit que les sites de son n° client
    def test_sco01_admin_sees_all_clients_scoped(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            s_a = self._create_site(admin_headers, f"SA{_uid()}", a["client"]["user_code"])
            s_b = self._create_site(admin_headers, f"SB{_uid()}", b["client"]["user_code"])
            s_global = self._create_site(admin_headers, f"SG{_uid()}", None)

            admin_sites = _api("GET", "/api/v1/sites", headers=admin_headers).json()
            assert all(s["site_id"] in {x["site_id"] for x in admin_sites} for s in (s_a, s_b, s_global))

            sites_a = _api("GET", "/api/v1/sites", headers=a["headers"]).json()
            assert len(sites_a) == 1
            assert sites_a[0]["site_id"] == s_a["site_id"]
            assert sites_a[0]["client_code"] == a["client"]["user_code"]

            sites_b = _api("GET", "/api/v1/sites", headers=b["headers"]).json()
            assert len(sites_b) == 1
            assert sites_b[0]["site_id"] == s_b["site_id"]

            r = _api("GET", f"/api/v1/sites/{s_b['site_id']}", headers=a["headers"])
            assert r.status_code == 404
            r = _api("GET", f"/api/v1/sites/{s_global['site_id']}", headers=a["headers"])
            assert r.status_code == 404
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])

    # SCO-02: un client ne voit/mode que ses postes ; postes d'un autre client inaccessibles
    def test_sco02_posts_scoped_and_isolated(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            s_a = self._create_site(admin_headers, f"SA{_uid()}", a["client"]["user_code"])
            s_b = self._create_site(admin_headers, f"SB{_uid()}", b["client"]["user_code"])

            post_a = self._create_post(a["headers"], s_a["site_id"], f"PA{_uid()}")
            post_b = self._create_post(b["headers"], s_b["site_id"], f"PB{_uid()}")

            posts_a = _api("GET", "/api/v1/posts", headers=a["headers"]).json()
            assert len(posts_a) == 1
            assert posts_a[0]["post_id"] == post_a["post_id"]

            r = _api("GET", f"/api/v1/posts/{post_b['post_id']}", headers=a["headers"])
            assert r.status_code == 404
            r = _api("GET", f"/api/v1/posts?site_id={s_b['site_id']}", headers=a["headers"])
            assert r.status_code == 200
            assert r.json() == []

            # Un client ne peut pas modifier ni supprimer un poste du voisin
            r = _api("PUT", f"/api/v1/posts/{post_b['post_id']}", json={
                "site_id": s_b["site_id"], "code": "ZZ", "name": "Pirat",
                "player_type": "Windows", "ip_address": "", "is_active": True,
            }, headers=a["headers"])
            assert r.status_code == 400
            r = _api("DELETE", f"/api/v1/posts/{post_b['post_id']}", headers=a["headers"])
            assert r.status_code == 400
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])

    # SCO-03: création d'un site par un client -> rattaché à SON n° client, payload client_code ignoré
    def test_sco03_client_creates_site_auto_tagged(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            r = _api("POST", "/api/v1/sites", json={
                "code": f"SC{_uid()}", "name": "Site client", "address": "",
                "description": "", "is_active": True, "client_code": b["client"]["user_code"],
            }, headers=a["headers"])
            assert r.status_code == 201, r.text
            created = r.json()
            # Le client ne peut pas tagger le site sous le code d'un autre client
            assert created["client_code"] == a["client"]["user_code"]

            # Le client A ne peut pas créer un poste sur un site du client B
            s_b = self._create_site(admin_headers, f"SB{_uid()}", b["client"]["user_code"])
            r = _api("POST", "/api/v1/posts", json={
                "site_id": s_b["site_id"], "code": f"PX{_uid()}", "name": "P",
                "player_type": "Windows", "ip_address": "", "is_active": True,
            }, headers=a["headers"])
            assert r.status_code == 400
            assert "n'existe pas" in r.json().get("detail", "")
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])

    # SCO-11: le code du COMPTE et le code du CLIENT sont deux choses
    # differentes. Un site cree par un compte dont le `user_code` ne vaut pas
    # le `code_client` de son client doit etre stocke sous le code CLIENT :
    # c'est sur ce code que filtre l'admin affecte a ce client, sinon il ne
    # voit rien de ce que ses comptes produisent.
    def test_sco11_admin_sees_content_created_by_its_accounts(self, admin_headers):
        import psycopg
        from tests._test_config import get_test_db_url

        client_code = f"CLI{_uid()}"
        _create_client_row(client_code)
        account_code, account_login = f"ACC{_uid()}", f"cliuser_{_uid()}"
        admin_code, admin_login = f"ADM{_uid()}", f"admcli_{_uid()}"
        account_id = admin_id = None

        try:
            # Un compte du profil « Utilisateur » rattache au client, avec un
            # `user_code` distinct du `code_client` (le cas qui etait casse).
            r = _api("POST", "/api/v1/users", json={
                "user_code": account_code, "login": account_login,
                "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD,
                "profile_id": 3, "is_active": True,
                "zones": [], "permissions": SITE_POST_PERMISSIONS,
            }, headers=admin_headers)
            assert r.status_code == 201, r.text
            account_id = r.json()["user_id"]

            # Le compte est rattache au bon client (et pas au client par defaut).
            # `POST /users` n'expose pas de champ client : le rattachement passe
            # par `user_code`, qui doit valoir un `code_client`. On ecrit donc
            # le `client_id` pour fabriquer le cas reellement casse, ou le code
            # du compte et celui du client different.
            conn = psycopg.connect(get_test_db_url())
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET client_id = "
                                "(SELECT id FROM clients WHERE code_client = %s) "
                                "WHERE user_id = %s", (client_code, account_id))
                    cur.execute("""SELECT c.code_client FROM users u
                                   JOIN clients c ON c.id = u.client_id
                                   WHERE u.user_id = %s""", (account_id,))
                    row = cur.fetchone()
                conn.commit()
            finally:
                conn.close()
            assert row[0] == client_code, f"compte rattache a {row[0]} au lieu de {client_code}"

            # Un admin affecte a ce client.
            r = _api("POST", "/api/v1/users", json={
                "user_code": admin_code, "login": admin_login,
                "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD,
                "profile_id": 1, "is_active": True,
                "zones": [], "permissions": SUPER_PERMISSIONS,
            }, headers=admin_headers)
            assert r.status_code == 201, r.text
            admin_id = r.json()["user_id"]
            upd = _api("PUT", f"/api/v1/admins/{admin_id}", json={
                "login": admin_login, "is_active": True, "client_codes": [client_code],
            }, headers=admin_headers)
            assert upd.status_code == 200, upd.text
            session = self._login(admin_login, None)
            adm_h = {"Authorization": f"Bearer {session['access_token']}",
                     "X-Device-Id": "pytest-device-0001"}

            # Le compte cree un site, puis un poste dessus.
            client_session = self._login(account_login, account_code)
            cli_h = {"Authorization": f"Bearer {client_session['access_token']}",
                     "X-Device-Id": "pytest-device-0001"}
            r = _api("POST", "/api/v1/sites", json={
                "code": f"CS{_uid()}", "name": "Site du compte", "address": "",
                "description": "", "is_active": True, "client_code": None,
            }, headers=cli_h)
            assert r.status_code == 201, r.text
            site = r.json()
            # Le site est stocke sous le code CLIENT, pas sous le code du compte.
            assert site["client_code"] == client_code, \
                f"stocke sous {site['client_code']} au lieu de {client_code}"

            post = self._create_post(cli_h, site["site_id"], f"CP{_uid()}")
            assert post["post_id"]

            # L'admin affecte au client voit le site ET le poste.
            sites = _api("GET", "/api/v1/sites", headers=adm_h).json()
            assert site["code"] in [s["code"] for s in sites], \
                "l'admin du client ne voit pas le site cree par son compte"
            posts = _api("GET", f"/api/v1/posts?site_id={site['site_id']}",
                         headers=adm_h).json()
            assert [p["post_id"] for p in posts] == [post["post_id"]], \
                "l'admin du client ne voit pas le poste cree par son compte"
        finally:
            for uid in (admin_id, account_id):
                if uid:
                    _api("DELETE", f"/api/v1/users/{uid}", headers=admin_headers)

    # SCO-04: le scope s'applique aux groupes (composition et postes du groupe limités au client)
    def test_sco04_groups_scoped(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            s_a = self._create_site(admin_headers, f"SA{_uid()}", a["client"]["user_code"])
            s_b = self._create_site(admin_headers, f"SB{_uid()}", b["client"]["user_code"])
            post_a = self._create_post(a["headers"], s_a["site_id"], f"PA{_uid()}")
            post_b = self._create_post(b["headers"], s_b["site_id"], f"PB{_uid()}")

            grp = _api("POST", "/api/v1/groups", json={
                "name": f"G{_uid()}", "description": "", "is_active": True,
            }, headers=admin_headers).json()
            gid = grp["group_id"]

            # L'admin ajoute les deux postes au groupe
            _api("PUT", f"/api/v1/groups/{gid}/membership", json={
                "post_ids": [post_a["post_id"], post_b["post_id"]],
            }, headers=admin_headers)

            # Le groupe doit être assigné aux clients pour qu'ils puissent y accéder
            self._assign_group(admin_headers, a["user"]["user_id"], [gid])
            self._assign_group(admin_headers, b["user"]["user_id"], [gid])

            # Client A ne voit dans la composition que son site et son poste ; le groupe ne compte qu'1 poste pour lui
            comp = _api("GET", f"/api/v1/groups/{gid}/composition", headers=a["headers"]).json()
            assert comp["post_count"] == 1
            assert {s["site_id"] for s in comp["sites"]} == {s_a["site_id"]}
            assert all(p["in_group"] is True for p in comp["sites"][0]["posts"])

            # Client A peut gérer son poste dans le groupe sans toucher à celui de B
            _api("DELETE", f"/api/v1/groups/{gid}/posts", json={
                "post_ids": [post_b["post_id"]],
            }, headers=a["headers"])
            comp_b = _api("GET", f"/api/v1/groups/{gid}/composition", headers=b["headers"]).json()
            assert comp_b["post_count"] == 1
            assert {p["post_id"] for s in comp_b["sites"] for p in s["posts"] if p["in_group"]} == {post_b["post_id"]}
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])

    # SCO-05: liste des sites avec recherche respecte le scope du client
    def test_sco05_search_respects_scope(self, admin_headers):
        a = self._client_headers(admin_headers)
        try:
            s_a = self._create_site(admin_headers, f"ZQ{_uid()}", a["client"]["user_code"])
            s_other = self._create_site(admin_headers, f"ZQ{_uid()}", None)
            r = _api("GET", "/api/v1/sites", params={"search": "ZQ"}, headers=a["headers"])
            assert r.status_code == 200
            assert [x["site_id"] for x in r.json()] == [s_a["site_id"]]
            assert s_other["site_id"] not in [x["site_id"] for x in r.json()]
        finally:
            self._delete_user(admin_headers, a["user"]["user_id"])

    # SCO-06: accès aux groupes par utilisateur — seul l'admin voit tout ;
    # un client ne voit que les groupes assignés et reçoit 403 pour les autres
    def test_sco06_groups_per_user_access(self, admin_headers):
        a = self._client_headers(admin_headers)
        b = self._client_headers(admin_headers)
        try:
            g1 = _api("POST", "/api/v1/groups", json={
                "name": f"GA{_uid()}", "description": "", "is_active": True,
            }, headers=admin_headers).json()["group_id"]
            g2 = _api("POST", "/api/v1/groups", json={
                "name": f"GB{_uid()}", "description": "", "is_active": True,
            }, headers=admin_headers).json()["group_id"]

            # L'admin voit les deux groupes
            admin_groups = _api("GET", "/api/v1/groups", headers=admin_headers).json()
            assert {g["group_id"] for g in admin_groups} >= {g1, g2}

            # Sans assignation, le client A ne voit aucun groupe
            groups_a = _api("GET", "/api/v1/groups", headers=a["headers"]).json()
            assert groups_a == []

            # Accès au détail d'un groupe non assigné -> 403
            r = _api("GET", f"/api/v1/groups/{g1}", headers=a["headers"])
            assert r.status_code == 403
            r = _api("GET", f"/api/v1/groups/{g1}/composition", headers=a["headers"])
            assert r.status_code == 403

            # On assigne g1 au client A : il le voit, mais pas g2
            self._assign_group(admin_headers, a["user"]["user_id"], [g1])
            groups_a = _api("GET", "/api/v1/groups", headers=a["headers"]).json()
            assert [g["group_id"] for g in groups_a] == [g1]
            r = _api("GET", f"/api/v1/groups/{g2}/composition", headers=a["headers"])
            assert r.status_code == 403

            # Le client B (non assigné) reçoit aussi 403
            r = _api("GET", f"/api/v1/groups/{g1}/composition", headers=b["headers"])
            assert r.status_code == 403
        finally:
            for c in (a, b):
                self._delete_user(admin_headers, c["user"]["user_id"])

    # SCO-07: retirer un groupe d'un utilisateur le rend inacessible
    def test_sco07_revoke_group(self, admin_headers):
        a = self._client_headers(admin_headers)
        try:
            g1 = _api("POST", "/api/v1/groups", json={
                "name": f"GR{_uid()}", "description": "", "is_active": True,
            }, headers=admin_headers).json()["group_id"]
            self._assign_group(admin_headers, a["user"]["user_id"], [g1])
            groups_a = _api("GET", "/api/v1/groups", headers=a["headers"]).json()
            assert [g["group_id"] for g in groups_a] == [g1]

            self._assign_group(admin_headers, a["user"]["user_id"], [])
            groups_a = _api("GET", "/api/v1/groups", headers=a["headers"]).json()
            assert groups_a == []
            r = _api("GET", f"/api/v1/groups/{g1}", headers=a["headers"])
            assert r.status_code == 403
        finally:
            self._delete_user(admin_headers, a["user"]["user_id"])

    # SCO-08: un client non-admin qui crée un groupe le voit immédiatement
    # (auto-assignation du groupe au créateur)
    def test_sco08_group_creation_auto_assigned(self, admin_headers):
        a = self._client_headers(admin_headers)
        try:
            r = _api("POST", "/api/v1/groups", json={
                "name": f"GC{_uid()}", "description": "", "is_active": True,
            }, headers=a["headers"])
            assert r.status_code == 201, r.text
            gid = r.json()["group_id"]

            # Le créateur voit son groupe et peut lire sa composition sans 403
            groups_a = _api("GET", "/api/v1/groups", headers=a["headers"]).json()
            assert [g["group_id"] for g in groups_a] == [gid]
            comp = _api("GET", f"/api/v1/groups/{gid}/composition", headers=a["headers"])
            assert comp.status_code == 200
        finally:
            self._delete_user(admin_headers, a["user"]["user_id"])

    # SCO-09: la supervision est limitée au périmètre client (client_code)
    def test_sco09_supervision_scoped_by_client(self, admin_headers):
        a = self._client_headers(admin_headers, permissions=SUPER_PERMISSIONS)
        b = self._client_headers(admin_headers, permissions=SUPER_PERMISSIONS)
        try:
            s_a = self._create_site(admin_headers, f"VSA{_uid()}", a["client"]["user_code"])
            s_b = self._create_site(admin_headers, f"VSB{_uid()}", b["client"]["user_code"])
            post_a = self._create_post(a["headers"], s_a["site_id"], f"VPA{_uid()}")
            post_b = self._create_post(b["headers"], s_b["site_id"], f"VPB{_uid()}")

            # L'admin voit les deux postes
            sup_admin = _api("GET", "/api/v1/supervision", headers=admin_headers).json()
            admin_posts = {p["post_id"] for s in sup_admin for p in s["posts"]}
            assert post_a["post_id"] in admin_posts and post_b["post_id"] in admin_posts

            # Le client A ne voit que son site et son poste
            sup_a = _api("GET", "/api/v1/supervision", headers=a["headers"]).json()
            assert sup_a
            a_posts = {p["post_id"] for s in sup_a for p in s["posts"]}
            assert a_posts == {post_a["post_id"]}
            assert {s["site_id"] for s in sup_a} == {s_a["site_id"]}

            # Le client A ne peut pinger que son poste (403 sur celui de B)
            r = _api("POST", f"/api/v1/posts/{post_b['post_id']}/ping", headers=a["headers"])
            assert r.status_code == 403
            r = _api("POST", f"/api/v1/posts/{post_a['post_id']}/ping", headers=a["headers"])
            assert r.status_code == 200
        finally:
            self._delete_user(admin_headers, a["user"]["user_id"])
            self._delete_user(admin_headers, b["user"]["user_id"])

    # SCO-10: la supervision inclut aussi les postes des groupes assignés
    # (union client + groupes), avec un user_code différent de celui du poste
    def test_sco10_supervision_scoped_by_group(self, admin_headers):
        a = self._client_headers(admin_headers, permissions=SUPER_PERMISSIONS)
        c = self._client_headers(admin_headers, permissions=SUPER_PERMISSIONS)
        try:
            s_a = self._create_site(admin_headers, f"WSA{_uid()}", a["client"]["user_code"])
            s_c = self._create_site(admin_headers, f"WSC{_uid()}", c["client"]["user_code"])
            post_a = self._create_post(a["headers"], s_a["site_id"], f"WPA{_uid()}")
            post_c = self._create_post(c["headers"], s_c["site_id"], f"WPC{_uid()}")

            # Groupe ne contenant que le poste de A
            g = _api("POST", "/api/v1/groups", json={
                "name": f"VG{_uid()}", "description": "", "is_active": True,
            }, headers=admin_headers).json()
            gid = g["group_id"]
            r = _api("PUT", f"/api/v1/groups/{gid}/membership", json={
                "post_ids": [post_a["post_id"]],
            }, headers=admin_headers)
            assert r.status_code == 200, r.text

            # Avant assignation : C ne voit que son propre poste, pas celui de A
            sup_c = _api("GET", "/api/v1/supervision", headers=c["headers"]).json()
            c_posts = {p["post_id"] for s in sup_c for p in s["posts"]}
            assert c_posts == {post_c["post_id"]}
            assert {s["site_id"] for s in sup_c} == {s_c["site_id"]}
            r = _api("POST", f"/api/v1/posts/{post_a['post_id']}/ping", headers=c["headers"])
            assert r.status_code == 403

            # On assigne le groupe à C : le poste de A devient visible et pingable
            self._assign_group(admin_headers, c["user"]["user_id"], [gid])
            sup_c = _api("GET", "/api/v1/supervision", headers=c["headers"]).json()
            c_posts = {p["post_id"] for s in sup_c for p in s["posts"]}
            assert c_posts == {post_a["post_id"], post_c["post_id"]}
            assert {s["site_id"] for s in sup_c} == {s_a["site_id"], s_c["site_id"]}
            r = _api("POST", f"/api/v1/posts/{post_a['post_id']}/ping", headers=c["headers"])
            assert r.status_code == 200
        finally:
            self._delete_user(admin_headers, a["user"]["user_id"])
            self._delete_user(admin_headers, c["user"]["user_id"])