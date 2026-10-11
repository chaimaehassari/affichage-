"""Partie 2 — règle 2.4 : création de rôles par un admin client.

Décision : un admin client (profil Administrateur, non superadmin) peut créer
des comptes de profils ÉGAUX OU INFÉRIEURS dans SON client, JAMAIS un rôle
plateforme, avec une trace d'audit à chaque création d'Administrateur. Aucune
élévation n'est possible.

Tests A1-A5 :
  A1 : profils égal (Administrateur) et inférieurs (Utilisateur, Superviseur) OK.
  A2 : profil inconnu refusé (400) ; `is_superadmin` injecté est ignoré.
  A3 : la création d'un Administrateur laisse une trace `admin_create`.
  A4 : les fonctions plateforme renvoient 403 à l'admin client.
  A5 : aucune création hors périmètre (client étranger) et pas d'élévation.
"""

import uuid

import psycopg
import pytest
import requests

from tests.conftest import (
    BASE_URL,
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    TEST_DEVICE,
    login_as,
    make_headers,
)
from tests._test_config import get_test_db_url

_TEST_PWD = "Test@1234"
_ADMIN_PERMS = [
    {"permission_id": 14, "can_view": True},
    {"permission_id": 11, "can_view": True, "can_create": True, "can_update": True, "can_delete": True},
]


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


@pytest.mark.v31
class TestAdminClientRoleRule:
    def _create_client(self, code):
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

    def _create_regular_admin(self, client_codes):
        """Crée un admin classique (profil 1) et lui affecte ses clients."""
        token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
        assert token
        login = f"v31adm_{_uid().lower()}"
        r = _api("POST", "/api/v1/users", json={
            "user_code": f"V31A{_uid()}",
            "login": login,
            "password": _TEST_PWD,
            "password_confirm": _TEST_PWD,
            "profile_id": 1,
            "is_active": True,
            "permissions": _ADMIN_PERMS,
        }, headers=make_headers(token))
        assert r.status_code == 201, r.text
        user_id = r.json()["user_id"]

        if client_codes:
            upd = _api("PUT", f"/api/v1/admins/{user_id}",
                       json={"login": login, "is_active": True,
                             "client_codes": list(client_codes)},
                       headers=make_headers(token))
            assert upd.status_code == 200, f"affectation clients: {upd.text}"

        tok = _api("POST", "/api/v1/auth/login",
                   json={"login": login, "password": _TEST_PWD},
                   headers={"X-Device-Id": TEST_DEVICE})
        assert tok.status_code == 200, f"login admin: {tok.status_code} {tok.text}"
        return {"user_id": user_id, "login": login, "token": tok.json()["access_token"]}

    def _user_payload(self, login, client_code, profile_id):
        return {
            "user_code": client_code,
            "login": login,
            "password": _TEST_PWD,
            "password_confirm": _TEST_PWD,
            "profile_id": profile_id,
            "is_active": True,
            "zones": [],
            "permissions": [],
        }

    def test_a1_admin_creates_equal_and_inferior_profiles(self):
        code = f"V31B{_uid()}"
        self._create_client(code)
        admin = self._create_regular_admin([code])
        h = make_headers(admin["token"])

        for profile_id, expected in ((1, "Administrateur"),
                                     (2, "Utilisateur"),
                                     (3, "Superviseur")):
            payload = self._user_payload(f"v31p{profile_id}_{_uid().lower()}", code, profile_id)
            r = _api("POST", "/api/v1/users", json=payload, headers=h)
            assert r.status_code == 201, f"profil {profile_id} refusé: {r.status_code} {r.text}"
            uid = r.json()["user_id"]

            detail = _api("GET", f"/api/v1/users/{uid}", headers=h)
            assert detail.status_code == 200, detail.text
            body = detail.json()
            assert body["profile_name"] == expected, body
            assert body["admin_id"] == admin["user_id"], \
                "le créateur doit devenir propriétaire du compte"

    def test_a2_unknown_profile_refused_and_no_superadmin(self):
        code = f"V31C{_uid()}"
        self._create_client(code)
        admin = self._create_regular_admin([code])
        h = make_headers(admin["token"])

        # Profil inexistant (ou futur profil plateforme) : refus explicite.
        bad = _api("POST", "/api/v1/users",
                   json=self._user_payload(f"v31bad_{_uid().lower()}", code, 999), headers=h)
        assert bad.status_code == 400, f"profil inconnu accepté: {bad.status_code} {bad.text}"

        # `is_superadmin` injecté dans le corps : ignoré (pas d'élévation).
        payload = self._user_payload(f"v31sx_{_uid().lower()}", code, 1)
        payload["is_superadmin"] = True
        r = _api("POST", "/api/v1/users", json=payload, headers=h)
        assert r.status_code == 201, r.text
        uid = r.json()["user_id"]

        detail = _api("GET", f"/api/v1/users/{uid}", headers=h)
        assert detail.status_code == 200, detail.text
        assert detail.json()["is_superadmin"] is False, "élévation Super Admin possible"

        conn = psycopg.connect(get_test_db_url())
        try:
            row = conn.execute(
                "SELECT is_superadmin FROM users WHERE user_id = %s", (uid,)
            ).fetchone()
        finally:
            conn.close()
        assert row is not None and row[0] is False, "is_superadmin enregistré en base"

    def test_a3_admin_creation_is_audited(self):
        code = f"V31D{_uid()}"
        self._create_client(code)
        admin = self._create_regular_admin([code])
        h = make_headers(admin["token"])

        payload = self._user_payload(f"v31aud_{_uid().lower()}", code, 1)
        r = _api("POST", "/api/v1/users", json=payload, headers=h)
        assert r.status_code == 201, r.text
        uid = r.json()["user_id"]

        conn = psycopg.connect(get_test_db_url())
        try:
            rows = conn.execute(
                """
                SELECT action, entity_type, entity_id, user_id
                FROM audit_logs
                WHERE action = 'admin_create' AND entity_id = %s
                """,
                (uid,),
            ).fetchall()
        finally:
            conn.close()

        assert rows, "aucune trace d'audit admin_create pour la création d'un Administrateur"
        action, entity_type, entity_id, actor_id = rows[0]
        assert action == "admin_create"
        assert entity_type == "user"
        assert int(entity_id) == int(uid)
        assert int(actor_id) == int(admin["user_id"]), "l'auteur du journal doit être le créateur"

    def test_a4_platform_functions_forbidden_for_admin_client(self):
        code = f"V31E{_uid()}"
        self._create_client(code)
        admin = self._create_regular_admin([code])
        h = make_headers(admin["token"])

        assert _api("GET", "/api/v1/admins", headers=h).status_code == 403
        assert _api("POST", "/api/v1/admins", json={
            "login": "x", "password": _TEST_PWD,
            "password_confirm": _TEST_PWD, "profile_id": 1,
        }, headers=h).status_code == 403
        assert _api("GET", "/api/v1/settings", headers=h).status_code == 403
        assert _api("GET", "/api/v1/ftp-profiles", headers=h).status_code == 403
        assert _api("POST", "/api/v1/settings/test-ftp", json={"host": "h"},
                    headers=h).status_code == 403
        assert _api("POST", "/api/v1/settings/regenerate-client-code",
                    headers=h).status_code == 403

    def test_a5_no_creation_out_of_perimeter(self):
        own = f"V31F{_uid()}"
        foreign = f"V31G{_uid()}"
        self._create_client(own)
        self._create_client(foreign)
        admin = self._create_regular_admin([own])
        h = make_headers(admin["token"])

        # Client d'un autre admin : refus.
        denied = _api("POST", "/api/v1/users",
                      json=self._user_payload(f"v31for_{_uid().lower()}", foreign, 3), headers=h)
        assert denied.status_code == 400, f"client tiers accepté: {denied.status_code} {denied.text}"

        # Son propre client : accepté, et rattaché à lui.
        ok = _api("POST", "/api/v1/users",
                  json=self._user_payload(f"v31own_{_uid().lower()}", own, 3), headers=h)
        assert ok.status_code == 201, ok.text
        uid = ok.json()["user_id"]
        detail = _api("GET", f"/api/v1/users/{uid}", headers=h).json()
        assert detail["admin_id"] == admin["user_id"]
        assert detail["is_superadmin"] is False
