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


_USER_CODES = {}


# --- Client de rattachement des sites -------------------------------------
# Regle metier : « un site appartient toujours a un client precis »
# (SiteService._resolve_client_id). Un site ne peut donc plus etre cree sans
# `client_code`, meme par le Super Admin. Ces tests creent donc leurs sites
# sous un vrai client, cree pour l'occasion puis supprime en fin de session.
_TEMP_CLIENTS: list[str] = []


def _client_code() -> str:
    """Cree un client jetable et renvoie son `code_client`."""
    import psycopg
    from tests._test_config import get_test_db_url
    code = "PRMCL" + _uid()
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 10, 50)",
                (code, f"Perm test client {code}"),
            )
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.append(code)
    return code


def _client_code_for_user(user_code: str) -> str:
    """Rattache le `user_code` du compte a un vrai client et renvoie son code.

    La regle « un site appartient toujours a un client » est resolue par
    `canonical_client_code`, qui traduit un `user_code` en `clients.code_client`
    via `users.client_id`. Ces comptes de test n'ont pas de client propre : on
    leur en cree un, auquel le site est rattache.
    """
    import psycopg
    from tests._test_config import get_test_db_url
    code = "PRMCU" + _uid()
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 10, 50)",
                (code, f"Perm client {code}"),
            )
            cur.execute(
                "UPDATE users SET client_id = (SELECT id FROM clients WHERE code_client = %s) "
                "WHERE user_code = %s",
                (code, user_code),
            )
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.append(code)
    return code


def pytest_sessionfinish(session, exitstatus):
    if not _TEMP_CLIENTS:
        return
    import psycopg
    from tests._test_config import get_test_db_url
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            for code in _TEMP_CLIENTS:
                cur.execute("DELETE FROM clients WHERE code_client = %s", (code,))
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.clear()


@pytest.fixture(scope="function")
def perm_map(admin_headers):
    r = _api("GET", "/api/v1/users/permissions", headers=admin_headers)
    assert r.status_code == 200, r.text
    return {p["code"]: p["permission_id"] for p in r.json()}


@pytest.fixture(scope="function")
def site_post(admin_headers):
    r = _api("POST", "/api/v1/sites", headers=admin_headers, json={
        "code": f"PRM_SITE_{_uid()}",
        "name": "Perm test site",
        "is_active": True,
        "client_code": _client_code(),
    })
    assert r.status_code == 201, r.text
    site_id = r.json()["site_id"]
    r2 = _api("POST", "/api/v1/posts", headers=admin_headers, json={
        "site_id": site_id,
        "code": f"PRM_POST_{_uid()}",
        "name": "Perm test post",
        "player_type": "Windows",
        "is_active": True,
    })
    assert r2.status_code == 201, r2.text
    return r2.json()["post_id"]


def _create_user(admin_headers, perm_map, codes=(), zones=(), view=True):
    login = f"perm{_uid().lower()}"
    client_code = f"C{_uid()}"
    perms = [
        {
            "permission_id": perm_map[c],
            "can_view": view,
            "can_create": False,
            "can_update": False,
            "can_delete": False,
        }
        for c in codes
    ]
    payload = {
        "user_code": client_code,
        "login": login,
        "password": "Test@1234",
        "password_confirm": "Test@1234",
        "profile_id": 2,
        "is_active": True,
        "zones": list(zones),
        "permissions": perms,
    }
    r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text

    _USER_CODES[login] = client_code
    return login


def _delete_user(admin_headers, login):
    r = _api("GET", "/api/v1/users", headers=admin_headers)
    if r.status_code != 200:
        return
    for u in r.json().get("users", []):
        if u["login"] == login:
            _api("DELETE", f"/api/v1/users/{u['user_id']}", headers=admin_headers)
            return


def _token(login, password="Test@1234"):
    body = {"login": login, "password": password}
    if login in _USER_CODES:
        body["client_code"] = _USER_CODES[login]
    r = _api("POST", "/api/v1/auth/login", json=body, headers={"X-Device-Id": "pytest-device-0001"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.v12
class TestPermissions:

    def test_admin_bypass(self, admin_headers):
        for path in ["/api/v1/users", "/api/v1/sites", "/api/v1/layouts",
                     "/api/v1/media", "/api/v1/supervision", "/api/v1/settings",
                     "/api/v1/groups"]:
            r = _api("GET", path, headers=admin_headers)
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text}"

    def test_read_only_user_cannot_write(self, admin_headers, perm_map):
        login = _create_user(admin_headers, perm_map, codes=("user_list",))
        h = {"Authorization": f"Bearer {_token(login)}"}
        r = _api("GET", "/api/v1/users", headers=h)
        assert r.status_code == 200, r.text
        r2 = _api("POST", "/api/v1/users", headers=h, json={
            "login": f"blocked_{_uid().lower()}",
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "is_active": True,
            "zones": [],
            "permissions": [],
        })
        assert r2.status_code == 403, r2.text
        r3 = _api("DELETE", "/api/v1/users/1", headers=h)
        assert r3.status_code == 403, r3.text
        _delete_user(admin_headers, login)

    def test_can_view_false_blocks(self, admin_headers, perm_map):
        login = _create_user(admin_headers, perm_map, codes=("user_list",), view=False)
        h = {"Authorization": f"Bearer {_token(login)}"}
        r = _api("GET", "/api/v1/users", headers=h)
        assert r.status_code == 403, r.text
        _delete_user(admin_headers, login)

    def test_site_post_write_permissions(self, admin_headers, perm_map):
        login = _create_user(admin_headers, perm_map, codes=("list_sites_posts",))
        h = {"Authorization": f"Bearer {_token(login)}"}
        r = _api("GET", "/api/v1/sites", headers=h)
        assert r.status_code == 200, r.text
        r2 = _api("POST", "/api/v1/sites", headers=h, json={
            "code": f"NOSITE_{_uid()}",
            "name": "Should fail",
            "is_active": True,
            "client_code": _client_code(),
        })
        assert r2.status_code == 403, r2.text
        _delete_user(admin_headers, login)

    def test_menu_permissions_gate_pages(self, admin_headers, perm_map, site_post):
        login = _create_user(admin_headers, perm_map, codes=("menu_media",))
        h = {"Authorization": f"Bearer {_token(login)}"}
        r = _api("GET", "/api/v1/media", headers=h)
        assert r.status_code == 200, r.text
        r2 = _api("GET", "/api/v1/layouts", headers=h)
        assert r2.status_code == 403, r2.text
        r3 = _api("GET", f"/api/v1/posts/{site_post}/sync-status", headers=h)
        assert r3.status_code == 403, r3.text
        _delete_user(admin_headers, login)

    def test_no_permissions_blocked(self, admin_headers, perm_map, site_post):
        login = _create_user(admin_headers, perm_map)
        h = {"Authorization": f"Bearer {_token(login)}"}
        for path in ["/api/v1/users", "/api/v1/sites", "/api/v1/layouts",
                     "/api/v1/media", "/api/v1/supervision", "/api/v1/settings",
                     "/api/v1/audit", f"/api/v1/posts/{site_post}/configuration",
                     f"/api/v1/posts/{site_post}/sync-status"]:
            r = _api("GET", path, headers=h)
            assert r.status_code == 403, f"{path} -> {r.status_code} {r.text}"
        _delete_user(admin_headers, login)

    def test_zone_scope_enforced(self, admin_headers, perm_map):
        login = _create_user(admin_headers, perm_map, codes=("menu_config",), zones=(3, 4))
        client_code = _USER_CODES.get(login)
        h = {"Authorization": f"Bearer {_token(login)}"}
        # Poste dédié rattaché au périmètre du client de l'utilisateur :
        # le scoping multi-tenant exige que les zones soient configurées sur
        # un poste appartenant au client de l'utilisateur.
        r_site = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": f"ZS_{_uid()}", "name": "Zone scope site", "is_active": True,
            "client_code": _client_code_for_user(client_code),
        })
        assert r_site.status_code == 201, r_site.text
        site_id = r_site.json()["site_id"]
        r_post = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site_id, "code": f"ZP_{_uid()}", "name": "Zone scope post",
            "player_type": "Windows", "is_active": True,
        })
        assert r_post.status_code == 201, r_post.text
        post_id = r_post.json()["post_id"]
        try:
            r = _api("POST", f"/api/v1/posts/{post_id}/zones", headers=h, json=[
                {"zone_number": 1, "media_id": None},
            ])
            assert r.status_code == 403, r.text
            r2 = _api("POST", f"/api/v1/posts/{post_id}/zones", headers=h, json=[
                {"zone_number": 3, "media_id": None},
            ])
            assert r2.status_code == 200, r2.text
        finally:
            _api("DELETE", f"/api/v1/posts/{post_id}", headers=admin_headers)
            _api("DELETE", f"/api/v1/sites/{site_id}", headers=admin_headers)
            _delete_user(admin_headers, login)

    def test_me_contains_zones_and_permissions(self, admin_headers, perm_map):
        login = _create_user(admin_headers, perm_map, codes=("user_list", "menu_config"),
                             zones=(5, 6))
        token = _token(login)
        r = _api("GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert sorted(data["zones"]) == [5, 6]
        codes = {p["code"] for p in data["permissions"]}
        assert "user_list" in codes and "menu_config" in codes
        _delete_user(admin_headers, login)