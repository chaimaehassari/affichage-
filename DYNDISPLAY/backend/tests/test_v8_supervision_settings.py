import uuid

import psycopg
import pytest
import requests

BASE_URL = "http://localhost:8000"
from tests._test_config import get_test_admin_password, get_test_db_url
DB_URL = get_test_db_url()
ADMIN_PASSWORD = get_test_admin_password()


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def make_auth(token):
    return {"Authorization": f"Bearer {token}"}


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
    def test_update_licenses_invalid_code_returns_400(self, admin_headers):
        r = _api("POST", "/api/v1/settings/license/update", json={"code": "BADCODE", "sites": 10, "posts": 20}, headers=admin_headers)
        assert r.status_code == 400


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
        account_code = r.json().get("account_code")
        from app.core.license_utils import generate_activation_code
        act_code = generate_activation_code(account_code)
        act = _api("POST", "/api/v1/auth/activate-account",
                   json={"login": login, "activation_code": act_code},
                   headers={"X-Device-Id": "pytest-device-0001"})
        assert act.status_code == 200, act.text
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
class TestSettings12SupremeAdminAccess:
    """CPS: écran Paramètres protégé par le code Supreme Admin
    (date du jour JJMMAAAA + suffixe fixe SUPREME_ADMIN_SECRET).

    Les tentatives sont journalisées dans audit_logs.
    """

    _SUPREME_SECRET = "X7K9"

    def test_today_code_accepted(self, admin_headers):
        from datetime import datetime
        today_code = datetime.now().astimezone().strftime("%d%m%Y") + self._SUPREME_SECRET
        r = _api("POST", "/api/v1/settings/verify-access",
                 json={"password": today_code}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json().get("valid") is True

    def test_raw_date_alone_rejected(self, admin_headers):
        # La date seule (JJMMAAAA) n'est plus un code valide.
        from datetime import datetime
        r = _api("POST", "/api/v1/settings/verify-access",
                 json={"password": datetime.now().astimezone().strftime("%d%m%Y")}, headers=admin_headers)
        assert r.status_code == 401

    def test_wrong_secret_rejected(self, admin_headers):
        # Date du jour + mauvais secret -> rejeté.
        from datetime import datetime
        bad_code = datetime.now().astimezone().strftime("%d%m%Y") + "AAAA"
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": bad_code}, headers=admin_headers)
        assert r.status_code == 401

    def test_other_day_code_rejected(self, admin_headers):
        # Bon secret mais date d'un autre jour -> rejeté.
        from datetime import datetime, timedelta
        other = (datetime.now().astimezone() + timedelta(days=1)).strftime("%d%m%Y") + self._SUPREME_SECRET
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": other}, headers=admin_headers)
        assert r.status_code == 401

    def test_wrong_code_rejected_with_audit(self, admin_headers):
        import psycopg as _pg
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": "000000"}, headers=admin_headers)
        assert r.status_code == 401
        with _pg.connect(DB_URL) as conn:
            row = conn.execute(
                """
                SELECT action FROM audit_logs
                WHERE action = 'supreme_admin_access_denied'
                ORDER BY audit_id DESC LIMIT 1
                """
            ).fetchone()
        assert row is not None and row[0] == "supreme_admin_access_denied"

    def test_old_hmac_code_rejected(self, admin_headers):
        # L'ancien code HMAC à 6 chiffres n'est plus accepté.
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": "783897"}, headers=admin_headers)
        assert r.status_code == 401

    def test_username_rejected_as_code(self, admin_headers):
        # Le nom d'utilisateur n'est jamais un code Supreme Admin valide.
        r = _api("POST", "/api/v1/settings/verify-access", json={"password": "admin"}, headers=admin_headers)
        assert r.status_code == 401


@pytest.mark.v8
class TestSettings13LicenseReductionBlocked:
    """CPS: impossible de réduire les licences sous le nombre de sites/postes réels."""

    def test_reduce_sites_below_used_returns_400(self, admin_headers):
        from app.core.license_utils import generate_license
        settings = _api("GET", "/api/v1/settings", headers=admin_headers).json()
        client_code = settings["code_client"]
        used_sites = settings["used_sites"]
        if used_sites < 1:
            pytest.skip("Aucun site actif en base")
        code = generate_license(client_code, used_sites - 1, settings["license_posts"])
        r = _api("POST", "/api/v1/settings/license/update",
                 json={"code": code, "sites": used_sites - 1, "posts": settings["license_posts"]},
                 headers=admin_headers)
        assert r.status_code == 400
        assert "réduire" in r.json().get("detail", "").lower() or "reduce" in r.json().get("detail", "").lower()

    def test_reduce_posts_below_used_returns_400(self, admin_headers):
        from app.core.license_utils import generate_license
        settings = _api("GET", "/api/v1/settings", headers=admin_headers).json()
        client_code = settings["code_client"]
        used_posts = settings["used_posts"]
        if used_posts < 1:
            pytest.skip("Aucun poste actif en base")
        code = generate_license(client_code, settings["license_sites"], used_posts - 1)
        r = _api("POST", "/api/v1/settings/license/update",
                 json={"code": code, "sites": settings["license_sites"], "posts": used_posts - 1},
                 headers=admin_headers)
        assert r.status_code == 400

    def test_increase_licenses_ok(self, admin_headers):
        from app.core.license_utils import generate_license
        settings = _api("GET", "/api/v1/settings", headers=admin_headers).json()
        client_code = settings["code_client"]
        used_sites = settings["used_sites"]
        used_posts = settings["used_posts"]
        # Augmentation réelle : au-dessus du quota courant ET du nombre utilisé en
        # base (sinon refused tant que used > quota, ce qui est le comportement voulu).
        target_sites = max(settings["license_sites"], used_sites) + 5
        target_posts = max(settings["license_posts"], used_posts) + 5
        code = generate_license(client_code, target_sites, target_posts)
        r = _api("POST", "/api/v1/settings/license/update",
                 json={"code": code, "sites": target_sites, "posts": target_posts},
                 headers=admin_headers)
        assert r.status_code == 200


@pytest.mark.v8
class TestSettings14DedicatedAccessPassword:
    """CPS: dès qu'un mot de passe d'accès dédié est défini
    (settings_access_hash), verify-access doit le vérifier (argon2, temps
    constant) ; sinon repli sur le code Supreme Admin (JJMMAAAA + suffixe secret)."""

    def test_dedicated_password_is_enforced(self, admin_headers):
        from datetime import datetime
        _clear_access_password()
        try:
            today_code = datetime.now().astimezone().strftime("%d%m%Y") + "X7K9"
            new_password = "Param@2026x"

            r = _api("POST", "/api/v1/settings/change-access-password",
                     json={"current_password": today_code, "new_password": new_password},
                     headers=admin_headers)
            assert r.status_code == 200, r.text

            ok = _api("POST", "/api/v1/settings/verify-access",
                      json={"password": new_password}, headers=admin_headers)
            assert ok.status_code == 200
            assert ok.json().get("valid") is True

            bad = _api("POST", "/api/v1/settings/verify-access",
                       json={"password": "Wrong@2026"}, headers=admin_headers)
            assert bad.status_code == 401

            date_rejected = _api("POST", "/api/v1/settings/verify-access",
                                 json={"password": today_code}, headers=admin_headers)
            assert date_rejected.status_code == 401
        finally:
            _clear_access_password()
