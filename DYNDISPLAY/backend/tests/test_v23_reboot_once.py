"""Redémarrage ponctuel (one-shot) — migration 022, ``posts.reboot_once_at``.

Volet backend. Le volet player (anti-boucle par instant via ``lastRebootAt``)
est couvert par ``tests/js/reboot_once_harness.cjs``, lancé par
``test_player_oneshot_guards``.

Couvert :
  * une date future est acceptée, propagée en UTC et relue ;
  * une date passée est REJETÉE en 422, avec le message attendu (pas de
    rattrapage) ;
  * un format invalide est rejeté en 422 avec le message de format ;
  * le champ repasse à NULL une fois la marge de grâce dépassée ;
  * absent du payload -> valeur conservée, ``null`` explicite -> annulation ;
  * récurrent et ponctuel cohabitent sans s'interférer.
"""

import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"
from tests._test_config import get_test_db_url

DB_URL = get_test_db_url()
HARNESS = Path(__file__).parent / "js" / "reboot_once_harness.cjs"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _once_payload(**overrides):
    """Payload de configuration minimal + reboot_once_at."""
    payload = {
        "layout_id": None,
        "loop_enabled": True,
        "schedule_enabled": False,
        "display_enabled": True,
        "zones": [],
    }
    payload.update(overrides)
    return payload


def _create_post() -> int:
    conn = psycopg.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            code = f"ONC{_uid()}"
            cur.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 10, 20) RETURNING id",
                (code, "Client one-shot"),
            )
            client_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO sites (code, name, address, description, is_active, client_code, client_id) "
                "VALUES (%s, %s, '', '', TRUE, %s, %s) RETURNING site_id",
                (code, "Site one-shot", code, client_id),
            )
            site_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO posts (site_id, code, name, is_active) VALUES (%s, %s, %s, TRUE) "
                "RETURNING post_id",
                (site_id, f"ONCP{_uid()}", "Poste one-shot"),
            )
            post_id = cur.fetchone()[0]
        conn.commit()
        return int(post_id)
    finally:
        conn.close()


def _drop_post(post_id: int) -> None:
    conn = psycopg.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            # Identifier le site et son client AVANT toute suppression : une fois
            # le post supprimé, il ne serait plus joignable via posts, le site ne
            # serait jamais purgé et le client resterait orphelin.
            cur.execute(
                "SELECT s.site_id, s.client_code FROM sites s "
                "JOIN posts p ON p.site_id = s.site_id WHERE p.post_id = %s",
                (post_id,),
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
            if row:
                cur.execute("DELETE FROM sites WHERE site_id = %s", (row[0],))
                cur.execute("DELETE FROM clients WHERE code_client = %s", (row[1],))
            # Filet de sécurité : clients de test sans site résiduel.
            cur.execute(
                "DELETE FROM clients WHERE code_client LIKE 'ONC%' "
                "AND NOT EXISTS (SELECT 1 FROM sites s WHERE s.client_code = clients.code_client)"
            )
        conn.commit()
    finally:
        conn.close()


def _row(post_id: int):
    conn = psycopg.connect(DB_URL)
    try:
        return conn.execute(
            "SELECT reboot_enabled, reboot_time, next_reboot_at, reboot_once_at "
            "FROM posts WHERE post_id = %s",
            (post_id,),
        ).fetchone()
    finally:
        conn.close()


def _set_once_db(post_id: int, value: datetime | None) -> None:
    """Pose directement reboot_once_at en base (préparation de fixture)."""
    conn = psycopg.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE posts SET reboot_once_at = %s WHERE post_id = %s",
                (value, post_id),
            )
        conn.commit()
    finally:
        conn.close()


def _app_now() -> datetime:
    from app.core.times import now_app

    return now_app()


def _local_future_iso(hours: int = 3) -> str:
    """Instant futur au format d'un <input type="datetime-local"> (naïf local)."""
    return (_app_now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


@pytest.mark.v23
class TestRebootOnceValidation:
    """Une date future passe, une date passée ou mal formée est rejetée."""

    def test_future_accepted_and_propagated(self, admin_headers):
        post_id = _create_post()
        try:
            url = f"/api/v1/posts/{post_id}/configuration"
            local = _local_future_iso(3)

            r = _api("PUT", url, headers=admin_headers, json=_once_payload(reboot_once_at=local))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_once_at"] is not None, body

            # Stocké en UTC, relu par le GET.
            row = _row(post_id)
            assert row[3] is not None, "reboot_once_at non écrit en base"
            assert row[3].tzinfo is not None, "reboot_once_at doit être aware (UTC)"
            assert abs((row[3] - _app_now().astimezone(timezone.utc)).total_seconds() - 3 * 3600) < 120

            g = _api("GET", url, headers=admin_headers)
            assert g.status_code == 200, g.text
            assert g.json()["reboot_once_at"] is not None
        finally:
            _drop_post(post_id)

    def test_past_rejected_with_detail(self, admin_headers):
        post_id = _create_post()
        try:
            url = f"/api/v1/posts/{post_id}/configuration"
            past = (_app_now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

            r = _api("PUT", url, headers=admin_headers, json=_once_payload(reboot_once_at=past))
            assert r.status_code == 422, r.text

            detail = r.json()["detail"]
            assert isinstance(detail, list) and detail, r.text
            entry = detail[0]
            assert entry["loc"] == ["body", "reboot_once_at"], entry
            assert entry["type"] == "value_error", entry
            assert entry["input"] == past, entry
            assert "futur" in entry["msg"], entry

            # Aucune écriture : le poste n'a jamais été modifié.
            assert _row(post_id)[3] is None
        finally:
            _drop_post(post_id)

    def test_invalid_format_rejected_with_detail(self, admin_headers):
        post_id = _create_post()
        try:
            url = f"/api/v1/posts/{post_id}/configuration"
            for bad in ("25:00", "2030/06/15 10:00", "hier", "2030-13-45T99:99"):
                r = _api("PUT", url, headers=admin_headers,
                         json=_once_payload(reboot_once_at=bad))
                assert r.status_code == 422, f"{bad} -> {r.status_code} : {r.text}"
                entry = r.json()["detail"][0]
                assert entry["loc"] == ["body", "reboot_once_at"], entry
                assert "YYYY-MM-DDTHH:MM" in entry["msg"], entry
            assert _row(post_id)[3] is None
        finally:
            _drop_post(post_id)


@pytest.mark.v23
class TestRebootOnceLifecycle:
    """Purge par déduction serveur + ausencia/annulation + non-interférence."""

    def test_nulled_after_grace_period(self, admin_headers):
        from app.services.reboot_schedule_service import REBOOT_ONCE_GRACE_MIN

        post_id = _create_post()
        try:
            now = datetime.now(timezone.utc)
            # Échéance dépassée depuis plus que la marge de grâce.
            _set_once_db(post_id, now - timedelta(minutes=REBOOT_ONCE_GRACE_MIN + 5))
            assert _row(post_id)[3] is not None

            url = f"/api/v1/posts/{post_id}/configuration"
            g = _api("GET", url, headers=admin_headers)
            assert g.status_code == 200, g.text
            assert g.json()["reboot_once_at"] is None, "le champ aurait dû être purgé"
            assert _row(post_id)[3] is None, "la purge doit aussi être persistée"
        finally:
            _drop_post(post_id)

    def test_kept_within_grace_period(self, admin_headers):
        from app.services.reboot_schedule_service import REBOOT_ONCE_GRACE_MIN

        post_id = _create_post()
        try:
            # Échéance dépassée, mais marge de grâce non écoulée : la demande
            # reste armée (le player a le temps de la récupérer).
            _set_once_db(
                post_id,
                datetime.now(timezone.utc) - timedelta(minutes=max(REBOOT_ONCE_GRACE_MIN - 5, 0)),
            )
            url = f"/api/v1/posts/{post_id}/configuration"
            g = _api("GET", url, headers=admin_headers)
            assert g.status_code == 200, g.text
            assert g.json()["reboot_once_at"] is not None, "la purge a été trop précoce"
            assert _row(post_id)[3] is not None
        finally:
            _drop_post(post_id)

    def test_absent_preserves_null_cancels(self, admin_headers):
        post_id = _create_post()
        try:
            url = f"/api/v1/posts/{post_id}/configuration"
            local = _local_future_iso(5)

            r = _api("PUT", url, headers=admin_headers, json=_once_payload(reboot_once_at=local))
            assert r.status_code == 200, r.text
            stored = _row(post_id)[3]
            assert stored is not None

            # Champ absent du payload -> conservé (un save du récurrent ne doit
            # pas effacer un one-shot programmé).
            r = _api("PUT", url, headers=admin_headers, json=_once_payload(reboot_enabled=False))
            assert r.status_code == 200, r.text
            assert _row(post_id)[3] == stored, "un PUT sans le champ doit conserver la valeur"

            # null explicite -> annulation.
            r = _api("PUT", url, headers=admin_headers,
                     json=_once_payload(reboot_once_at=None))
            assert r.status_code == 200, r.text
            assert r.json()["reboot_once_at"] is None
            assert _row(post_id)[3] is None
        finally:
            _drop_post(post_id)

    def test_recurring_and_once_do_not_interfere(self, admin_headers):
        """Les deux mécanismes activés en même temps restent indépendants."""
        from app.core.times import get_app_tz

        post_id = _create_post()
        try:
            url = f"/api/v1/posts/{post_id}/configuration"
            tz = get_app_tz()
            hour = (datetime.now(tz) + timedelta(hours=2)).strftime("%H:%M")

            r = _api("PUT", url, headers=admin_headers, json=_once_payload(
                reboot_enabled=True, reboot_time=hour, reboot_once_at=_local_future_iso(6),
            ))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_enabled"] is True
            assert body["reboot_time"] == hour
            assert body["next_reboot_at"] is not None
            once_before = body["reboot_once_at"]
            assert once_before is not None

            # Désactiver le RÉCURRENT ne doit pas toucher au ponctuel...
            r = _api("PUT", url, headers=admin_headers,
                     json=_once_payload(reboot_enabled=False, reboot_time=hour))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reboot_enabled"] is False
            assert body["reboot_once_at"] == once_before, "le récurrent a effacé le ponctuel"
            assert _row(post_id)[3] is not None

            # ...et la purge du ponctuel ne doit pas casser le récurrent.
            r = _api("PUT", url, headers=admin_headers, json=_once_payload(
                reboot_enabled=True, reboot_time=hour, reboot_once_at=_local_future_iso(7),
            ))
            assert r.status_code == 200, r.text
            new_once = r.json()["reboot_once_at"]
            _set_once_db(post_id, datetime.now(timezone.utc) - timedelta(hours=1))

            g = _api("GET", url, headers=admin_headers)
            assert g.status_code == 200, g.text
            body = g.json()
            assert body["reboot_once_at"] is None, "ponctuel non purgé"
            assert body["reboot_enabled"] is True, "le ponctuel a désactivé le récurrent"
            assert body["reboot_time"] == hour
            assert body["next_reboot_at"] is not None
            assert new_once is not None
        finally:
            _drop_post(post_id)

    def test_config_json_payload_exposes_once(self):
        """Le config.json de la synchro porte reboot_once_at (chemin player)."""
        from psycopg.rows import dict_row

        from app.services.sync_service import SyncService

        post_id = _create_post()
        # SyncService lit les lignes par nom de colonne (dict_row), comme le
        # pool de l'application.
        conn = psycopg.connect(DB_URL, row_factory=dict_row)
        try:
            _set_once_db(post_id, datetime.now(timezone.utc) + timedelta(hours=4))
            payload = SyncService(conn).generate_config(post_id)
            assert payload["reboot_once_at"] is not None, payload

            # Purge : le champ disparaît du config.json, le player ne voit plus
            # de one-shot armé.
            _set_once_db(post_id, datetime.now(timezone.utc) - timedelta(hours=1))
            payload = SyncService(conn).generate_config(post_id)
            assert payload["reboot_once_at"] is None, payload
        finally:
            conn.close()
            _drop_post(post_id)


@pytest.mark.v23
class TestPlayerOneShotGuards:
    """Volet player : anti-boucle par instant (lastRebootAt) vs par jour."""

    def test_player_oneshot_guards(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node introuvable : harnais player non exécuté")
        proc = subprocess.run(
            [node, str(HARNESS)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0 and " introuvable" in proc.stdout:
            pytest.skip("rebootOnce.js introuvable (checkout partiel ?)")
        assert proc.returncode == 0, (
            f"harnais player en échec :\n{proc.stdout}\n{proc.stderr}"
        )
        # Le harnais doit avoir couvert le cas des deux one-shots le même jour.
        assert "PLAYER ONESHOT OK" in proc.stdout
