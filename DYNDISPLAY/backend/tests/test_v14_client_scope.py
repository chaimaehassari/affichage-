import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"


def _api(method, path, **kwargs):
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


@pytest.mark.v14
class TestClientScope:

    def _create_client(self, admin_headers, requires_activation=True):
        user_code = f"SCO{_uid()}"
        login = f"cliscope_{_uid()}"
        payload = {
            "user_code": user_code,
            "login": login,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "profile_id": 2,
            "is_active": True,
            "requires_activation": requires_activation,
            "zones": [],
            "permissions": SITE_POST_PERMISSIONS,
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
        })
        assert r.status_code == 200, r.text
        return r.json()

    def _activate(self, headers, user_code, sites=5, posts=20):
        from app.core.license_utils import generate_license
        code = generate_license(user_code, sites, posts)
        r = _api("POST", "/api/v1/auth/activate", json={"code": code}, headers=headers)
        assert r.status_code == 200, r.text

    def _client_headers(self, admin_headers):
        c = self._create_client(admin_headers, requires_activation=True)
        u = self._find_user(admin_headers, c["login"])
        session = self._login(c["login"], c["user_code"])
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        self._activate(headers, c["user_code"])
        return {"client": c, "user": u, "headers": headers}

    def _create_site(self, admin_headers, code, client_code=None):
        payload = {
            "code": code, "name": f"Site {code}", "address": "",
            "description": "", "is_active": True, "client_code": client_code or None,
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