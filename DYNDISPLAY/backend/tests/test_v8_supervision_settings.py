import uuid
from datetime import datetime

import psycopg
import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_admin_password, get_test_db_url
from tests.conftest import ADMIN_LOGIN, login_as, make_headers, unlock_admin
DB_URL = get_test_db_url()
ADMIN_PASSWORD = get_test_admin_password()


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


def make_auth(token):
    return {"Authorization": f"Bearer {token}", "X-Device-Id": "pytest-device-0001"}


def _make_site_post():
    """Create a site + post via a committed connection.
    Returns (site_id, post_id) as ints."""
    with psycopg.connect(DB_URL) as conn:
        site = conn.execute(
            "INSERT INTO sites (code, name, is_active, client_id) VALUES (%s, %s, TRUE, (SELECT id FROM clients ORDER BY id LIMIT 1)) RETURNING site_id",
            (f"S{uuid.uuid4().hex[:6].upper()}", "V8 Site"),
        ).fetchone()
        site_id = site[0]
        post = conn.execute(
            """
            INSERT INTO posts (site_id, code, name, is_active)
            VALUES (%s, %s, %s, TRUE) RETURNING post_id
            """,
            (site_id, f"P{uuid.uuid4().hex[:6].upper()}", "V8 Post"),
        ).fetchone()
        conn.commit()
        return site_id, int(post[0])


def _destroy_site_post(site_id, post_id):
    """Delete a committed site + post via a fresh committed connection."""
    with psycopg.connect(DB_URL) as conn:
        conn.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
        conn.execute("DELETE FROM sites WHERE site_id = %s", (site_id,))
        conn.commit()


# Licence gérée par client (PUT /api/v1/clients/{code}/license) : les tests
# ci-dessous créent des clients jetables, supprimés en fin de session.
_TEMP_CLIENTS: list[str] = []


def _client_code() -> str:
    code = "V8CL" + uuid.uuid4().hex[:8].upper()
    with psycopg.connect(DB_URL) as conn:
        conn.execute(
            "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
            "VALUES (%s, %s, 10, 50)",
            (code, f"V8 client {code}"),
        )
        conn.commit()
    _TEMP_CLIENTS.append(code)
    return code


def pytest_sessionfinish(session, exitstatus):
    if not _TEMP_CLIENTS:
        return
    with psycopg.connect(DB_URL) as conn:
        conn.execute(
            "DELETE FROM clients WHERE code_client = ANY(%s)",
            (list(_TEMP_CLIENTS),),
        )
        conn.commit()
    _TEMP_CLIENTS.clear()


# ---------------------------------------------------------------------------
# SUPER-* : Supervision
# ---------------------------------------------------------------------------

@pytest.mark.v8
class TestSuper01SupervisionList:
    def test_supervision_returns_sites(self, admin_headers):
        r = _api("GET", "/api/v1/supervision", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        for site in body:
            assert "site_id" in site
            assert "code" in site
            assert "name" in site
            assert "posts" in site
            assert isinstance(site["posts"], list)


@pytest.mark.v8
class TestSuper02SupervisionPostFields:
    def test_post_fields_present(self, admin_headers):
        site_id, post_id = _make_site_post()
        try:
            r = _api("GET", "/api/v1/supervision", headers=admin_headers)
            assert r.status_code == 200
            sites = r.json()
            site_entry = next((s for s in sites if s["site_id"] == site_id), None)
            assert site_entry is not None
            post_entry = next(
                (p for p in site_entry["posts"] if p["post_id"] == post_id), None
            )
            assert post_entry is not None
            assert "is_online" in post_entry
            assert "is_up_to_date" in post_entry
            assert "last_sync_at" in post_entry
            assert "last_heartbeat_at" in post_entry
            assert "display_enabled" in post_entry
            assert "status" in post_entry
            assert post_entry["status"] == "offline"
        finally:
            _destroy_site_post(site_id, post_id)


@pytest.mark.v8
class TestSuper06Heartbeat:
    def test_heartbeat_marks_online(self, admin_headers):
        site_id, post_id = _make_site_post()
        try:
            r = _api("POST", "/api/v1/posts/heartbeat", json={"post_id": post_id})
            assert r.status_code == 200

            with psycopg.connect(DB_URL) as conn:
                row = conn.execute(
                    "SELECT is_online, last_heartbeat_at FROM posts WHERE post_id = %s",
                    (post_id,),
                ).fetchone()
                assert row is not None
                assert row[0] is True
                assert row[1] is not None
        finally:
            _destroy_site_post(site_id, post_id)

    def test_heartbeat_nonexistent_post_returns_404(self, admin_headers):
        r = _api("POST", "/api/v1/posts/heartbeat", json={"post_id": 99999})
        assert r.status_code == 404


@pytest.mark.v8
class TestSuper07Ping:
    """CPS: ping ICMP réel vers l'adresse IP d'un poste (connecté ou non)."""

    def _make_post_with_ip(self, ip):
        with psycopg.connect(DB_URL) as conn:
            site = conn.execute(
                "INSERT INTO sites (code, name, is_active, client_id) VALUES (%s, %s, TRUE, (SELECT id FROM clients ORDER BY id LIMIT 1)) RETURNING site_id",
                (f"S{uuid.uuid4().hex[:6].upper()}", "V8 Ping Site"),
            ).fetchone()
            site_id = site[0]
            post = conn.execute(
                """
                INSERT INTO posts (site_id, code, name, ip_address, is_active)
                VALUES (%s, %s, %s, %s, TRUE) RETURNING post_id
                """,
                (site_id, f"P{uuid.uuid4().hex[:6].upper()}", "V8 Ping Post", ip),
            ).fetchone()
            conn.commit()
            return site_id, int(post[0])

    def _destroy(self, site_id, post_id):
        with psycopg.connect(DB_URL) as conn:
            conn.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
            conn.execute("DELETE FROM sites WHERE site_id = %s", (site_id,))
            conn.commit()

    def test_ping_reachable_post(self, admin_headers):
        site_id, post_id = self._make_post_with_ip("127.0.0.1")
        try:
            r = _api("POST", f"/api/v1/posts/{post_id}/ping", headers=admin_headers)
            assert r.status_code == 200
            body = r.json()
            assert body.get("reachable") is True
            assert "rtt_ms" in body
            assert body["rtt_ms"] is not None
        finally:
            self._destroy(site_id, post_id)

    def test_ping_unreachable_post(self, admin_headers):
        # 192.0.2.1 est une adresse de test non routable -> injoignable.
        site_id, post_id = self._make_post_with_ip("192.0.2.1")
        try:
            r = _api("POST", f"/api/v1/posts/{post_id}/ping", headers=admin_headers)
            assert r.status_code == 200
            body = r.json()
            assert body.get("reachable") is False
        finally:
            self._destroy(site_id, post_id)

    def test_ping_without_ip(self, admin_headers):
        site_id, post_id = self._make_post_with_ip(None)
        try:
            r = _api("POST", f"/api/v1/posts/{post_id}/ping", headers=admin_headers)
            assert r.status_code == 200
            assert r.json().get("reachable") is False
            assert "adresse ip" in r.json().get("message", "").lower()
        finally:
            self._destroy(site_id, post_id)


# ---------------------------------------------------------------------------
# SETTINGS-* : Settings protection, licences, FTP profiles
# ---------------------------------------------------------------------------

@pytest.mark.v8
class TestSettings01ClientCodeVerify:
    def test_wrong_code_returns_401(self, admin_headers):
        r = _api("POST", "/api/v1/settings/verify-client-code", json={"code": "WRONGCODE"}, headers=admin_headers)
        assert r.status_code == 401

    def test_correct_code_returns_valid(self, admin_headers):
        # A valid code equals the current user's connection password (seedé, cf. ADMIN_PASSWORD).
        r = _api("POST", "/api/v1/settings/verify-client-code", json={"code": ADMIN_PASSWORD}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json().get("valid") is True


@pytest.mark.v8
class TestSettings02GetSettings:
    def test_get_settings_returns_required_keys(self, admin_headers):
        r = _api("GET", "/api/v1/settings", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "display_mode" not in body
        assert "license_sites" in body
        assert "license_posts" in body
        assert "used_sites" in body
        assert "used_posts" in body
        assert "code_client" in body


@pytest.mark.v8
class TestSettings04UpdateSettings:
    def test_display_mode_not_accepted(self, admin_headers):
        r = _api("PUT", "/api/v1/settings", json={"display_mode": "tableau"}, headers=admin_headers)
        assert r.status_code == 200
        assert "display_mode" not in r.json()


@pytest.mark.v8
class TestSettings06LicenseInvalidCode:
    def test_update_licenses_unknown_client_returns_404(self, admin_headers):
        r = _api("PUT", "/api/v1/clients/BADCODE2026/license",
                 json={"license_sites": 10, "license_posts": 20}, headers=admin_headers)
        assert r.status_code == 404

    def test_update_licenses_negative_values_returns_422(self, admin_headers):
        code = _client_code()
        r = _api("PUT", f"/api/v1/clients/{code}/license",
                 json={"license_sites": -1, "license_posts": 20}, headers=admin_headers)
        assert r.status_code == 422


@pytest.mark.v8
class TestSettings07FtpProfilesCRUD:
    def test_create_list_update_delete(self, admin_headers):
        r = _api("POST", "/api/v1/ftp-profiles", headers=admin_headers, json={
            "name": f"Test FTP {__import__('uuid').uuid4().hex[:6]}",
            "server_address": "127.0.0.1",
            "port": 21,
            "username": "user",
            "password": "secret",
            "security_mode": "NONE",
            "transfer_mode": "BINARY",
            "passive_mode": True,
            "timeout": 30,
        })
        assert r.status_code == 201
        profile = r.json()
        profile_id = profile["profile_id"]

        r_list = _api("GET", "/api/v1/ftp-profiles", headers=admin_headers)
        assert r_list.status_code == 200
        assert any(p["profile_id"] == profile_id for p in r_list.json())

        r_upd = _api("PUT", f"/api/v1/ftp-profiles/{profile_id}", headers=admin_headers, json={"port": 2222})
        assert r_upd.status_code == 200
        assert r_upd.json()["port"] == 2222

        r_del = _api("DELETE", f"/api/v1/ftp-profiles/{profile_id}", headers=admin_headers)
        assert r_del.status_code == 200


@pytest.mark.v8
class TestSettings09FtpTestInvalid:
    def test_ftp_test_nonexistent_profile(self, admin_headers):
        r = _api("POST", "/api/v1/settings/test-ftp", json={"profile_id": 99999}, headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body.get("success") is False


@pytest.mark.v8
class TestSettings10ChangePasswordValidation:
    """CPS: password complexity rules must apply to the self-service change."""

    def test_change_password_rejects_short(self, admin_headers):
        r = _api("POST", "/api/v1/settings/change-password", headers=admin_headers,
                 json={"current_password": ADMIN_PASSWORD, "new_password": "abc"})
        assert r.status_code == 422

    def test_change_password_rejects_weak(self, admin_headers):
        r = _api("POST", "/api/v1/settings/change-password", headers=admin_headers,
                 json={"current_password": ADMIN_PASSWORD, "new_password": "abcdefg1"})
        assert r.status_code == 422

    def test_change_password_rejects_wrong_current(self, admin_headers):
        r = _api("POST", "/api/v1/settings/change-password", headers=admin_headers,
                 json={"current_password": "wrongpass", "new_password": "Ab12345!zz"})
        assert r.status_code == 400


def _login_user(login, password, client_code=None):
    body = {"login": login, "password": password}
    if client_code:
        body["client_code"] = client_code
    return requests.post(f"{BASE_URL}/api/v1/auth/login", json=body, headers={"X-Device-Id": "pytest-device-0001"})


@pytest.mark.v8
class TestSettings11ForcedPasswordChange:
    """CPS: must_change_password must be flagged on create/reset, unflagged on self-service change."""

    def _create_user(self, token):
        login = f"pwd_{uuid.uuid4().hex[:8]}"
        client_code = f"PC{uuid.uuid4().hex[:8]}"
        payload = {
            "user_code": client_code,
            "login": login,
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 2,
            "is_active": True,
            "zones": [1],
            "permissions": [],
        }
        r = _api("POST", "/api/v1/users", json=payload, headers=make_auth(token))
        assert r.status_code == 201, r.text
        return login, client_code

    def test_forced_flag_and_self_service_change(self, admin_headers):
        login, client_code = self._create_user(admin_headers["Authorization"].replace("Bearer ", ""))
        try:
            resp = _login_user(login, "Test@1234", client_code)
            assert resp.status_code == 200
            me = resp.json()["user"]
            assert me["must_change_password"] is True

            user_token = resp.json()["access_token"]
            headers = make_auth(user_token)

            ok = _api("POST", "/api/v1/settings/change-password", headers=headers,
                      json={"current_password": "Test@1234", "new_password": "NewPass@88"})
            assert ok.status_code == 200, ok.text

            me2 = _api("GET", "/api/v1/auth/me", headers=headers)
            assert me2.status_code == 200
            assert me2.json()["must_change_password"] is False
        finally:
            r_list = _api("GET", "/api/v1/users", headers=admin_headers)
            uid = next((u["user_id"] for u in r_list.json().get("users", []) if u["login"] == login), None)
            if uid:
                _api("DELETE", f"/api/v1/users/{uid}", headers=admin_headers)


def _clear_access_password():
    with psycopg.connect(DB_URL) as conn:
        conn.execute("DELETE FROM general_settings WHERE setting_key = 'settings_access_hash'")
        conn.commit()


@pytest.mark.v8
class TestSettings12SettingsAccessUsesLoginPassword:
    """CPS: l'écran Paramètres se déverrouille avec CE QUI A OUVRT L'APP.

    Il n'existe plus de mot de passe d'accès dédié (`settings_access_hash`).
    La chaîne acceptée est celle du compte authentifié :

      - le mot de passe du compte (`users.password_hash`) ;
      - et, UNIQUEMENT pour l'Admin suprême, le code du jour
        (JJMMAAAA + SUPREME_ADMIN_SECRET), car c'est cette chaîne-là qui
        ouvre la session via `_try_supreme_admin_login` (routes/auth.py).
        Ne pas l'accepter rendait la page Paramètres inaccessible au
        Super Admin : la chaîne qui venait d'ouvrir l'application était
        rejetée par la porte suivante.

    Un Admin classique doit, lui, toujours présenter SON mot de passe.
    """

    def test_login_password_accepted(self, admin_headers):
        r = _api("POST", "/api/v1/settings/verify-access",
                 json={"password": ADMIN_PASSWORD}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json().get("valid") is True

    def test_wrong_password_rejected_with_audit(self, admin_headers):
        import psycopg as _pg
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": "000000"}, headers=admin_headers)
        assert r.status_code == 401
        with _pg.connect(DB_URL) as conn:
            row = conn.execute(
                """
                SELECT action FROM audit_logs
                WHERE action = 'settings_access_denied'
                ORDER BY audit_id DESC LIMIT 1
                """
            ).fetchone()
        assert row is not None and row[0] == "settings_access_denied"

    def test_login_itself_rejected(self, admin_headers):
        # Ni le login, ni un ancien code ne sont acceptés.
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": ADMIN_LOGIN}, headers=admin_headers)
        assert r.status_code == 401

    def test_daily_supreme_code_accepted_for_superadmin(self, admin_headers):
        """Le code du jour ouvre l'application ET les paramètres du Super Admin.

        C'était le bug corrigé : le code était refusé ici alors qu'il venait
        juste de permettre la connexion.
        """
        from datetime import datetime
        today_code = datetime.now().astimezone().strftime("%d%m%Y") + "X7K9"
        r = _api("POST", "/api/v1/settings/verify-access",
                 json={"password": today_code}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json().get("valid") is True

    def _create_regular_admin(self, admin_headers):
        """Crée un admin classique (non Admin suprême), activé et connecté."""
        token = admin_headers["Authorization"].replace("Bearer ", "")
        login = f"set12_{uuid.uuid4().hex[:8]}"
        client_code = f"S12{uuid.uuid4().hex[:8]}"
        r = _api("POST", "/api/v1/users", headers=make_auth(token), json={
            "user_code": client_code,
            "login": login,
            "password": "Test@1234",
            "password_confirm": "Test@1234",
            "profile_id": 1,  # Administrateur (droits Paramètres), mais PAS Admin suprême
            "is_active": True,
            "zones": [1],
            "permissions": [],
        })
        assert r.status_code == 201, r.text
        r_me = _api("GET", "/api/v1/auth/me", headers=make_auth(token))
        assert r_me.status_code == 200, r_me.text
        resp = _login_user(login, "Test@1234", client_code)
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"].get("is_superadmin") is False
        return login, "Test@1234", make_auth(resp.json()["access_token"])

    def _delete_user(self, admin_headers, login):
        r_list = _api("GET", "/api/v1/users", headers=admin_headers)
        uid = next((u["user_id"] for u in r_list.json().get("users", []) if u["login"] == login), None)
        if uid:
            _api("DELETE", f"/api/v1/users/{uid}", headers=admin_headers)

    def test_daily_supreme_code_rejected_for_regular_admin(self, admin_headers):
        """Un Admin classique n'obtient rien du code du jour."""
        from datetime import datetime
        today_code = datetime.now().astimezone().strftime("%d%m%Y") + "X7K9"
        login, password, headers = self._create_regular_admin(admin_headers)
        try:
            r = _api("POST", "/api/v1/settings/verify-access",
                     json={"password": today_code}, headers=headers)
            assert r.status_code == 401, r.text
            # ... mais SON propre mot de passe reste accepté.
            r2 = _api("POST", "/api/v1/settings/verify-access",
                      json={"password": password}, headers=headers)
            assert r2.status_code == 200, r2.text
        finally:
            self._delete_user(admin_headers, login)

    def test_legacy_hmac_code_rejected(self, admin_headers):
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": "783897"}, headers=admin_headers)
        assert r.status_code == 401

    def test_no_dedicated_access_password_endpoint(self, admin_headers):
        # Le mot de passe d'accès dédié a été supprimé.
        spec = _api("GET", "/openapi.json").json()
        assert "/api/v1/settings/change-access-password" not in spec["paths"]
        r = _api("POST", "/api/v1/settings/change-access-password",
                 json={"current_password": ADMIN_PASSWORD, "new_password": "Param@2026x"},
                 headers=admin_headers)
        # 404 (route inconnue) ou 405 (route supprimée, un autre verbe matche) :
        # dans les deux cas l'endpoint n'est plus appelable.
        assert r.status_code in (404, 405), r.text

    def test_stale_settings_access_hash_is_ignored(self, admin_headers):
        """Un settings_access_hash resté en base ne doit plus rienouvrir."""
        from app.core.security import hash_password
        stale = "Legacy@2026"
        with psycopg.connect(DB_URL) as conn:
            conn.execute(
                """
                INSERT INTO general_settings (setting_key, setting_value, description, updated_at)
                VALUES ('settings_access_hash', %s, 'legacy', NOW())
                ON CONFLICT (setting_key)
                DO UPDATE SET setting_value = EXCLUDED.setting_value
                """,
                (hash_password(stale),),
            )
            conn.commit()
        try:
            r = _api("POST", "/api/v1/settings/verify-access", json={"password": stale}, headers=admin_headers)
            assert r.status_code == 401
            ok = _api("POST", "/api/v1/settings/verify-access",
                      json={"password": ADMIN_PASSWORD}, headers=admin_headers)
            assert ok.status_code == 200
        finally:
            _clear_access_password()


@pytest.mark.v8
class TestSettings13LicenseUpdatePerClient:
    """CPS: les quotas de licences sont gérés par CLIENT via
    PUT /api/v1/clients/{code}/license. L'ancien endpoint global
    /settings/license/update (vérifié par signature T2F) est supprimé :
    le quota est un simple compteur qu'on augmente ou réduit. La réduction
    en deçà du nombre de sites/postes réels est donc acceptée.
    """

    def _put(self, admin_headers, code, sites, posts):
        r = _api("PUT", f"/api/v1/clients/{code}/license",
                 json={"license_sites": sites, "license_posts": posts},
                 headers=admin_headers)
        assert r.status_code == 200, r.text
        return r.json()

    def test_reduce_sites_below_used_returns_200(self, admin_headers):
        code = _client_code()
        body = self._put(admin_headers, code, 1, 50)
        assert body["license_sites"] == 1

    def test_reduce_posts_below_used_returns_200(self, admin_headers):
        code = _client_code()
        body = self._put(admin_headers, code, 10, 0)
        assert body["license_posts"] == 0

    def test_increase_licenses_ok(self, admin_headers):
        code = _client_code()
        body = self._put(admin_headers, code, 500, 2000)
        assert body["license_sites"] == 500
        assert body["license_posts"] == 2000


@pytest.mark.v8
class TestSettings14AdminScopeAutoAssignment:
    """CPS: un Admin créé sans client sélectionné ne doit pas être un compte mort.

    `admin_clients` est la seule source du périmètre d'un Admin classique. Sans
    ligne, l'admin ne voyait aucun client et `POST /users` refusait avec
    « Aucun client ne vous est affecté : impossible de rattacher un utilisateur. »
    """

    def _create_admin(self, client_codes):
        # Login direct (hors fixture `admin_token`) : on déverrouille d'abord,
        # car les tests de mot de passe faux des autres fichiers peuvent avoir
        # verrouillé le compte admin entre-temps.
        unlock_admin()
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        assert token, "login admin impossible (compte verrouillé ?)"
        payload = {
            "login": f"scopeauto{uuid.uuid4().hex[:8]}",
            "password": "Scope@2026x",
            "password_confirm": "Scope@2026x",
            "client_codes": client_codes,
        }
        r = _api("POST", "/api/v1/admins", json=payload, headers=make_headers(token))
        assert r.status_code == 201, r.text
        return r.json()

    def test_no_client_selected_still_gets_a_usable_scope(self):
        created = self._create_admin([])
        assert created["client_codes"], "un admin sans client ne peut rien faire"
        # Le repli donne UN client, jamais l'ensemble des clients.
        assert len(created["client_codes"]) == 1
        # L'auto-affectation est signalée, elle n'est pas silencieuse.
        assert created["auto_assigned_client"] == created["client_codes"][0]

    def test_admin_without_scope_can_create_user(self):
        """Le vrai symptôme : POST /users ne doit plus échouer en 400."""
        created = self._create_admin([])
        admin_token = login_as(created["login"], "Scope@2026x")
        assert admin_token, "l'admin créé doit pouvoir se connecter"

        import psycopg as _pg
        with _pg.connect(DB_URL) as conn:
            profile_id = conn.execute(
                "SELECT profile_id FROM profiles WHERE name <> 'Administrateur' ORDER BY profile_id LIMIT 1"
            ).fetchone()[0]

        stamp = uuid.uuid4().hex[:8]
        r = _api("POST", "/api/v1/users", json={
            "login": f"scopeprobe{stamp}",
            "password": "Usr@2026xyz",
            "password_confirm": "Usr@2026xyz",
            "profile_id": profile_id,
        }, headers=make_headers(admin_token))
        assert r.status_code == 201, r.text
        # L'utilisateur créé est rattaché au client de l'admin.
        assert r.json().get("user_code") == created["client_codes"][0]


@pytest.mark.v8
class TestSettings15ClientCodeAlphanumeric:
    """CPS: le code client signé dans les licences accepte lettres ET chiffres.

    Même règle que l'app Android « Licence T2F » (8 caractères maximum,
    normalisés en majuscules) : le backend ne doit pas pouvoir enregistrer un
    code que l'app refuserait de signer.
    """

    def _stored_code(self):
        with psycopg.connect(DB_URL) as conn:
            row = conn.execute(
                "SELECT setting_value FROM general_settings WHERE setting_key = 'code_client'"
            ).fetchone()
            return row[0] if row else None

    def _restore(self, original):
        # Restauration directe en base : la valeur d'origine peut dater
        # d'avant la règle des 8 caractères et serait refusée par l'API.
        with psycopg.connect(DB_URL) as conn:
            conn.execute(
                "UPDATE general_settings SET setting_value = %s WHERE setting_key = 'code_client'",
                (original,),
            )
            conn.commit()

    @pytest.mark.parametrize("raw,expected", [
        ("ABC123", "ABC123"),
        ("T2F2026", "T2F2026"),
        ("CLT001A", "CLT001A"),
        ("  abc123  ", "ABC123"),
    ])
    def test_alphanumeric_code_accepted_and_normalized(self, admin_headers, raw, expected):
        original = self._stored_code()
        try:
            r = _api("PUT", "/api/v1/settings", json={"code_client": raw}, headers=admin_headers)
            assert r.status_code == 200, r.text
            assert r.json()["code_client"] == expected
            assert _api("GET", "/api/v1/settings", headers=admin_headers).json()["code_client"] == expected
        finally:
            self._restore(original)

    @pytest.mark.parametrize("raw", ["ABC12345X", "ABCDEFGHI", "ABC-123", "ABC_123", "ABC 123", ""])
    def test_invalid_code_refused_422(self, admin_headers, raw):
        original = self._stored_code()
        try:
            r = _api("PUT", "/api/v1/settings", json={"code_client": raw}, headers=admin_headers)
            assert r.status_code == 422, r.text
            assert "caract" in r.text.lower() or "code client" in r.text.lower()
            # La valeur en base n'a pas bougé.
            assert self._stored_code() == original
        finally:
            self._restore(original)

    def test_license_quotas_with_alphanumeric_code_accepted(self, admin_headers):
        """Le code client (normalisé, alphanumérique) est accepté par l'endpoint
        licence par client : la génération des codes vit côté player (boîte T2F),
        le backend n'accepte que des codes clients alphanumériques normalisés."""
        from app.core.license_utils import normalize_client_code
        code = normalize_client_code(" t2f2026 ")
        assert code == "T2F2026"
        with psycopg.connect(DB_URL) as conn:
            conn.execute("DELETE FROM clients WHERE code_client = %s", (code,))
            conn.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 10, 50)",
                (code, f"Client {code}"),
            )
            conn.commit()
        _TEMP_CLIENTS.append(code)
        up = _api("PUT", f"/api/v1/clients/{code}/license",
                  json={"license_sites": 5, "license_posts": 20},
                  headers=admin_headers)
        assert up.status_code == 200, up.text
        body = up.json()
        assert body["license_sites"] == 5
        assert body["license_posts"] == 20
