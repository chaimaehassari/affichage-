import uuid
from datetime import datetime, time as dtime, timedelta, timezone

import pytest
import requests
import psycopg
from psycopg.rows import dict_row

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_db_url

DB_URL = get_test_db_url()
TEST_PASSWORD = "Test@1234"
DEVICE_ID = "pytest-device-rbs-0001"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


@pytest.mark.v22
class TestRebootSchedule:
    """Programmation de redémarrage (migration 021).

    - ``reboot_time`` invalide → 422 (rejet par PostConfigurationUpdate).
    - ``compute_next_reboot_at`` / ``refresh_next_reboot_at`` : heure du jour
      déjà passée → lendemain ; sinon aujourd'hui ; échéance uniquement future.
    - ``batch-reboot-schedule`` : un poste hors périmètre ou inexistant est
      écarté (failed) sans jamais être modifié, avec une raison lisible.
    - Mélange valides / invalides → compteurs et raisons exacts.
    """

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _login(login: str) -> dict:
        r = _api("POST", "/api/v1/auth/login", json={"login": login, "password": TEST_PASSWORD},
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
                    INSERT INTO clients (code_client, nom_client,
                                         license_sites, license_posts)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (code, f"Client {code}", 10, 20),
                )
                client_id = cur.fetchone()[0]
            conn.commit()
            return client_id
        finally:
            conn.close()

    @staticmethod
    def _create_admin_db(admin_headers: dict) -> dict:
        """Crée un Admin classique (rôle Admin Client) via POST /admins."""
        login = f"rbsadmin_{_uid().lower()}"
        r = _api("POST", "/api/v1/admins", json={
            "user_code": f"RBS{_uid()}",
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
    def _create_site_post(client_code: str, client_id: int) -> int:
        """Crée un site + un poste rattachés au client. Retourne post_id."""
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sites (code, name, address, description, is_active,
                                       client_code, client_id)
                    VALUES (%s, %s, '', '', TRUE, %s, %s)
                    RETURNING site_id
                    """,
                    (f"RBSSITE{_uid()}", f"Site {client_code}", client_code, client_id),
                )
                site_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO posts (site_id, code, name, is_active)
                    VALUES (%s, %s, %s, TRUE) RETURNING post_id
                    """,
                    (site_id, f"RBSPOST{_uid()}", f"Poste {client_code}"),
                )
                post_id = cur.fetchone()[0]
            conn.commit()
            return int(post_id)
        finally:
            conn.close()

    @staticmethod
    def _reboot_row(post_id: int):
        conn = psycopg.connect(DB_URL)
        try:
            row = conn.execute(
                "SELECT reboot_enabled, reboot_time, next_reboot_at "
                "FROM posts WHERE post_id = %s",
                (post_id,),
            ).fetchone()
            return row
        finally:
            conn.close()

    @staticmethod
    def _set_reboot_time(post_id: int, value: str):
        """Pose directement reboot_time en base (préparation de fixture)."""
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE posts SET reboot_time = %s WHERE post_id = %s",
                    (value, post_id),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _cleanup(client_codes=(), user_ids=()):
        if not (client_codes or user_ids):
            return
        conn = psycopg.connect(DB_URL)
        try:
            with conn.cursor() as cur:
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

    # --- 1) reboot_time invalide → 422 (PostConfigurationUpdate) ----------

    def test_post_config_rejects_invalid_reboot_time(self, admin_headers):
        from app.core.times import get_app_tz
        tz = get_app_tz()
        cl = f"RBSIA{_uid()}"
        cl_id = self._create_client_db(cl)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers)
            assert self._assign(admin_headers, admin["user_id"], cl).status_code == 201
            ah = self._login(admin["login"])

            post_id = self._create_site_post(cl, cl_id)
            url = f"/api/v1/posts/{post_id}/configuration"

            for bad in ("25:00", "12:60", "9:00", "0900", "01:0a"):
                r = _api("PUT", url, headers=ah, json={
                    "layout_id": None,
                    "loop_enabled": True,
                    "schedule_enabled": False,
                    "display_enabled": True,
                    "zones": [],
                    "reboot_enabled": True,
                    "reboot_time": bad,
                })
                assert r.status_code == 422, f"{bad} → {r.status_code} : {r.text}"
                # Aucune écriture : le poste n'a jamais été modifié.
                row = self._reboot_row(post_id)
                assert row[0] is False and row[1] is None and row[2] is None

            # Heure valide dans le futur → accepté.
            future_hm = (datetime.now(tz) + timedelta(hours=2)).strftime("%H:%M")
            r = _api("PUT", url, headers=ah, json={
                "layout_id": None,
                "loop_enabled": True,
                "schedule_enabled": False,
                "display_enabled": True,
                "zones": [],
                "reboot_enabled": True,
                "reboot_time": future_hm,
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_enabled"] is True
            assert body["reboot_time"] == future_hm
            assert body["next_reboot_at"] is not None
        finally:
            self._cleanup(client_codes=[cl], user_ids=[admin["user_id"]] if admin else [])

    # --- 2) compute/refresh next_reboot_at (passé → lendemain) -------------

    def test_compute_next_reboot_at_past_time_jumps_to_next_day(self):
        from app.core.times import get_app_tz, now_app, to_utc
        from app.services.reboot_schedule_service import compute_next_reboot_at

        tz = get_app_tz()
        now = now_app()

        # Heure du jour déjà passée (00:00 est toujours <= maintenant) → demain.
        nxt = compute_next_reboot_at("00:00")
        local = nxt.astimezone(tz)
        assert local.hour == 0 and local.minute == 0
        today = now.date()
        assert local.date() == today + timedelta(days=1), local.isoformat()

        # Échéance strictement future, jamais dans le passé.
        assert nxt > datetime.now(timezone.utc)

    def test_refresh_next_reboot_at_sets_and_advances(self):
        from app.core.times import get_app_tz
        from app.services.reboot_schedule_service import refresh_next_reboot_at

        tz = get_app_tz()
        cl = f"RBSRF{_uid()}"
        cl_id = self._create_client_db(cl)
        try:
            post_id = self._create_site_post(cl, cl_id)
            future_hm = (datetime.now(tz) + timedelta(hours=2)).strftime("%H:%M")

            # row_factory=dict_row : convention du backend (tous les pools
            # l'imposent), le service lit ses lignes par NOM de colonne.
            conn = psycopg.connect(DB_URL, row_factory=dict_row)
            try:
                with conn.transaction():
                    conn.execute(
                        "UPDATE posts SET reboot_enabled = TRUE, reboot_time = %s, "
                        "next_reboot_at = NULL WHERE post_id = %s",
                        (future_hm, post_id),
                    )
                    res = refresh_next_reboot_at(conn, post_id)
                assert res["reboot_enabled"] is True
                assert res["reboot_time"] == future_hm
                assert res["next_reboot_at"] is not None
                assert datetime.fromisoformat(res["next_reboot_at"].replace("Z", "+00:00")) \
                    > datetime.now(timezone.utc)

                # Échéance délibérément dépassée → recalculée au prochain jour.
                with conn.transaction():
                    conn.execute(
                        "UPDATE posts SET next_reboot_at = now() - interval '1 hour' "
                        "WHERE post_id = %s",
                        (post_id,),
                    )
                    res2 = refresh_next_reboot_at(conn, post_id)
                assert res2["next_reboot_at"] is not None
                assert datetime.fromisoformat(res2["next_reboot_at"].replace("Z", "+00:00")) \
                    > datetime.now(timezone.utc)

                # Passée à 00:00 → lendemain.
                with conn.transaction():
                    conn.execute(
                        "UPDATE posts SET reboot_time = '00:00', next_reboot_at = NULL "
                        "WHERE post_id = %s",
                        (post_id,),
                    )
                    res3 = refresh_next_reboot_at(conn, post_id)
                local = datetime.fromisoformat(res3["next_reboot_at"].replace("Z", "+00:00")).astimezone(tz)
                assert local.hour == 0 and local.minute == 0
                assert local.date() == (datetime.now(tz) + timedelta(days=1)).date()
            finally:
                conn.close()
        finally:
            self._cleanup(client_codes=[cl])

    # --- 3) batch : hors périmètre / introuvable → jamais modifié ----------

    def test_batch_reboot_out_of_scope_never_modified(self, admin_headers):
        cla = f"RBSOA{_uid()}"
        clb = f"RBSOB{_uid()}"
        cla_id = self._create_client_db(cla)
        clb_id = self._create_client_db(clb)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers)
            assert self._assign(admin_headers, admin["user_id"], cla).status_code == 201
            ah = self._login(admin["login"])

            a1 = self._create_site_post(cla, cla_id)
            b1 = self._create_site_post(clb, clb_id)

            r = _api("POST", "/api/v1/posts/batch-reboot-schedule", headers=ah, json={
                "post_ids": [a1, b1, 99999999],
                "reboot_enabled": True,
                "reboot_time": "08:30",
                "sync": False,
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success_count"] == 1
            assert body["synced_post_ids"] == []  # sync=False
            assert sorted(body["failed_ids"]) == sorted([b1, 99999999])

            reasons = {f["post_id"]: f["reason"] for f in body["failed_posts"]}
            assert reasons[b1] == "hors de votre périmètre"
            assert reasons[99999999] == "introuvable"

            # Le poste du client B n'a JAMAIS été modifié.
            row_b = self._reboot_row(b1)
            assert row_b[0] is False and row_b[1] is None and row_b[2] is None

            # Le poste dans le périmètre, lui, est bien programmé.
            # psycopg renvoie la colonne TIME en datetime.time (jamais "HH:MM").
            row_a = self._reboot_row(a1)
            assert row_a[0] is True and row_a[1] == dtime(8, 30) and row_a[2] is not None
        finally:
            self._cleanup(client_codes=[cla, clb], user_ids=[admin["user_id"]] if admin else [])

    # --- 4) batch : mélange valides / invalides → compteurs exacts ---------

    def test_batch_reboot_mix_valid_invalid_counters(self, admin_headers):
        cla = f"RBSMC{_uid()}"
        clb = f"RBSMD{_uid()}"
        cla_id = self._create_client_db(cla)
        clb_id = self._create_client_db(clb)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers)
            assert self._assign(admin_headers, admin["user_id"], cla).status_code == 201
            ah = self._login(admin["login"])

            ok1 = self._create_site_post(cla, cla_id)
            ok2 = self._create_site_post(cla, cla_id)
            no_time = self._create_site_post(cla, cla_id)   # heure jamais posée
            outside = self._create_site_post(clb, clb_id)
            ghost = 88888888

            r = _api("POST", "/api/v1/posts/batch-reboot-schedule", headers=ah, json={
                "post_ids": [ok1, ok2, no_time, outside, ghost],
                "reboot_enabled": True,
                "reboot_time": "22:15",
                "sync": False,
            })
            assert r.status_code == 200, r.text
            body = r.json()
            # L'heure EST fournie dans la requête : elle s'applique à tous les
            # postes du périmètre, y compris celui qui n'avait aucune heure.
            # Seuls les postes hors périmètre / inexistants sont écartés.
            assert body["success_count"] == 3
            assert body["synced_post_ids"] == []
            assert sorted(body["failed_ids"]) == sorted([outside, ghost])

            reasons = {f["post_id"]: f["reason"] for f in body["failed_posts"]}
            assert reasons[outside] == "hors de votre périmètre"
            assert reasons[ghost] == "introuvable"

            # Les 3 postes du périmètre sont programmés à 22:15.
            for pid in (ok1, ok2, no_time):
                row = self._reboot_row(pid)
                assert row[0] is True and row[1] == dtime(22, 15) and row[2] is not None
            # Le poste hors périmètre n'a JAMAIS été modifié.
            row_outside = self._reboot_row(outside)
            assert row_outside[0] is False and row_outside[1] is None
        finally:
            self._cleanup(client_codes=[cla, clb], user_ids=[admin["user_id"]] if admin else [])

    def test_batch_reboot_without_time_keeps_stored_hour_or_fails(self, admin_headers):
        """``reboot_time`` absent : on réutilise l'heure déjà enregistrée.

        - poste avec heure existante → reprogrammé sur cette heure (fallback) ;
        - poste sans aucune heure → écarté, raison « heure manquante », intact.
        """
        cla = f"RBSNF{_uid()}"
        cla_id = self._create_client_db(cla)
        admin = None
        try:
            admin = self._create_admin_db(admin_headers)
            assert self._assign(admin_headers, admin["user_id"], cla).status_code == 201
            ah = self._login(admin["login"])

            stored = self._create_site_post(cla, cla_id)
            self._set_reboot_time(stored, "05:45")
            never = self._create_site_post(cla, cla_id)

            r = _api("POST", "/api/v1/posts/batch-reboot-schedule", headers=ah, json={
                "post_ids": [stored, never],
                "reboot_enabled": True,
                "reboot_time": None,
                "sync": False,
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success_count"] == 1
            assert body["failed_ids"] == [never]

            reasons = {f["post_id"]: f["reason"] for f in body["failed_posts"]}
            assert reasons[never] == "heure manquante"

            # Fallback sur l'heure existante, et le poste sans heure intact.
            row_stored = self._reboot_row(stored)
            assert row_stored[0] is True and row_stored[1] == dtime(5, 45)
            assert row_stored[2] is not None
            row_never = self._reboot_row(never)
            assert row_never[0] is False and row_never[1] is None and row_never[2] is None
        finally:
            self._cleanup(client_codes=[cla], user_ids=[admin["user_id"]] if admin else [])