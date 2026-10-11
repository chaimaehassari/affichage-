"""Phase 2, Partie 3 — Option B : stockage média adressé par contenu intra-client.

Un seul fichier physique par (client_code, sha256) ; plusieurs lignes `media`
(liens : nom/dossier distincts) peuvent le référencer. Le fichier n'est supprimé
que lorsque le dernier lien du client est supprimé (ref_count = 0).

Tests M1..M9 (voir RAPPORT_PHASE1 ... et l'accord Phase 2).
"""
import io
import os
import struct
import uuid
import zlib

import psycopg
import pytest
import requests
from psycopg.rows import dict_row

from tests._test_config import get_test_db_url

BASE_URL = os.environ.get("TEST_BASE_URL") or "http://localhost:8000"
TEST_PASSWORD = "Test@1234"


def _api(method, path, **kwargs):
    headers = kwargs.get("headers") or {}
    if "Authorization" in headers:
        kwargs = {**kwargs, "headers": {"X-Device-Id": "pytest-device-0001", **headers}}
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:8].upper()


def _seed():
    return int(uuid.uuid4().hex[:8], 16)


def _png(seed):
    """PNG minimal dont le CONTENU (donc le sha256) dépend de `seed`."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc & 0xFFFFFFFF)
    b0 = (seed >> 16) & 0xFF
    b1 = (seed >> 8) & 0xFF
    b2 = seed & 0xFF
    raw = zlib.compress(bytes([b0, b1, b2, 0]))
    idat_crc = zlib.crc32(b"IDAT" + raw)
    idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc & 0xFFFFFFFF)
    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


def _conn():
    return psycopg.connect(get_test_db_url(), row_factory=dict_row)


def _media_row(media_id):
    with _conn() as conn:
        return conn.execute(
            "SELECT media_id, name, sftp_path, checksum, client_code FROM media WHERE media_id = %s",
            (media_id,),
        ).fetchone()


def _store_exists(path):
    from app.services.media_storage import get_media_store

    with get_media_store() as store:
        return store.exists(path)


CLIENT_PERMISSIONS = [
    {"permission_id": 11, "can_view": True},                       # menu_media
    {"permission_id": 15, "can_create": True, "can_view": True},   # create_site
    {"permission_id": 18, "can_create": True, "can_view": True},   # create_post
]

_TEMP_CLIENTS: list[str] = []
_TEMP_GROUPS: list[int] = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    if not (_TEMP_CLIENTS or _TEMP_GROUPS):
        return
    conn = _conn()
    try:
        if _TEMP_GROUPS:
            conn.execute("DELETE FROM screen_groups WHERE group_id = ANY(%s)", (_TEMP_GROUPS,))
        if _TEMP_CLIENTS:
            site_ids = [
                r["site_id"]
                for r in conn.execute(
                    "SELECT site_id FROM sites WHERE client_code = ANY(%s)", (_TEMP_CLIENTS,)
                ).fetchall()
            ]
            if site_ids:
                conn.execute("DELETE FROM posts WHERE site_id = ANY(%s)", (site_ids,))
            conn.execute("DELETE FROM media WHERE client_code = ANY(%s)", (_TEMP_CLIENTS,))
            conn.execute("DELETE FROM users WHERE user_code = ANY(%s)", (_TEMP_CLIENTS,))
            conn.execute("DELETE FROM sites WHERE client_code = ANY(%s)", (_TEMP_CLIENTS,))
            conn.execute("DELETE FROM clients WHERE code_client = ANY(%s)", (_TEMP_CLIENTS,))
        conn.commit()
    finally:
        conn.close()
        _TEMP_CLIENTS.clear()
        _TEMP_GROUPS.clear()


def _create_client(admin_headers):
    user_code = f"MD{_uid()}"
    with _conn() as conn:
        conn.execute(
            "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
            "VALUES (%s, %s, 10, 50)",
            (user_code, f"Client {user_code}"),
        )
    _TEMP_CLIENTS.append(user_code)
    login = f"md_{_uid()}"
    payload = {
        "user_code": user_code,
        "login": login,
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "profile_id": 2,
        "is_active": True,
        "zones": [1, 2, 3, 4],
        "permissions": CLIENT_PERMISSIONS,
    }
    r = _api("POST", "/api/v1/users", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    return {"user_code": user_code, "login": login}


def _client_headers(admin_headers):
    client = _create_client(admin_headers)
    r = _api(
        "POST",
        "/api/v1/auth/login",
        json={"login": client["login"], "password": TEST_PASSWORD, "client_code": client["user_code"]},
        headers={"X-Device-Id": "pytest-device-0001"},
    )
    assert r.status_code == 200, r.text
    return {"client": client, "headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}


def _upload(headers, name, data):
    return _api(
        "POST",
        "/api/v1/media/upload",
        headers=headers,
        files={"file": (name, io.BytesIO(data), "image/png")},
    )


def _delete(headers, media_id):
    return _api("DELETE", f"/api/v1/media/{media_id}", headers=headers)


@pytest.mark.v30
class TestMediaDedupOptionB:

    # M1 — même client, même contenu, noms différents => 1 fichier, 2 liens.
    def test_m1_intra_client_links_share_one_file(self, admin_headers):
        a = _client_headers(admin_headers)
        data = _png(_seed())
        r1 = _upload(a["headers"], f"m1a_{_uid()}.png", data)
        r2 = _upload(a["headers"], f"m1b_{_uid()}.png", data)
        assert r1.status_code == 201, r1.text
        assert r2.status_code == 201, r2.text
        row1 = _media_row(r1.json()["media_id"])
        row2 = _media_row(r2.json()["media_id"])
        assert row1["media_id"] != row2["media_id"]
        assert row1["sftp_path"] == row2["sftp_path"]
        assert row1["checksum"] == row2["checksum"]
        assert _store_exists(row1["sftp_path"]) is True

    # M1bis — même client, même contenu, MÊME nom => 409 (comportement historique).
    def test_m1bis_same_name_same_content_is_409(self, admin_headers):
        a = _client_headers(admin_headers)
        data = _png(_seed())
        name = f"m1dup_{_uid()}.png"
        r1 = _upload(a["headers"], name, data)
        assert r1.status_code == 201, r1.text
        r2 = _upload(a["headers"], name, data)
        assert r2.status_code == 409, r2.text

    # M2 — deux clients, même contenu => 2 fichiers physiques distincts.
    def test_m2_cross_client_same_content_two_files(self, admin_headers):
        a = _client_headers(admin_headers)
        b = _client_headers(admin_headers)
        data = _png(_seed())
        ra = _upload(a["headers"], f"m2a_{_uid()}.png", data)
        rb = _upload(b["headers"], f"m2b_{_uid()}.png", data)
        assert ra.status_code == 201, ra.text
        assert rb.status_code == 201, rb.text
        path_a = _media_row(ra.json()["media_id"])["sftp_path"]
        path_b = _media_row(rb.json()["media_id"])["sftp_path"]
        assert path_a != path_b
        assert _store_exists(path_a) and _store_exists(path_b)

    # M3 — même client, contenus différents => 2 fichiers distincts.
    def test_m3_same_client_different_content_two_files(self, admin_headers):
        a = _client_headers(admin_headers)
        r1 = _upload(a["headers"], f"m3a_{_uid()}.png", _png(_seed()))
        r2 = _upload(a["headers"], f"m3b_{_uid()}.png", _png(_seed()))
        assert r1.status_code == 201 and r2.status_code == 201
        p1 = _media_row(r1.json()["media_id"])["sftp_path"]
        p2 = _media_row(r2.json()["media_id"])["sftp_path"]
        assert p1 != p2

    # M4 — supprimer UN lien ne supprime pas le fichier (autre lien du même client).
    def test_m4_delete_one_link_keeps_file(self, admin_headers):
        a = _client_headers(admin_headers)
        data = _png(_seed())
        r1 = _upload(a["headers"], f"m4a_{_uid()}.png", data)
        r2 = _upload(a["headers"], f"m4b_{_uid()}.png", data)
        id1 = r1.json()["media_id"]
        id2 = r2.json()["media_id"]
        path = _media_row(id1)["sftp_path"]
        d = _delete(a["headers"], id1)
        assert d.status_code == 200, d.text
        assert _media_row(id1) is None
        assert _media_row(id2) is not None
        assert _store_exists(path) is True

    # M5 — supprimer le DERNIER lien retire le fichier physique.
    def test_m5_delete_last_link_removes_file(self, admin_headers):
        a = _client_headers(admin_headers)
        data = _png(_seed())
        r1 = _upload(a["headers"], f"m5a_{_uid()}.png", data)
        r2 = _upload(a["headers"], f"m5b_{_uid()}.png", data)
        id1 = r1.json()["media_id"]
        id2 = r2.json()["media_id"]
        path = _media_row(id1)["sftp_path"]
        assert _delete(a["headers"], id1).status_code == 200
        assert _store_exists(path) is True
        assert _delete(a["headers"], id2).status_code == 200
        assert _media_row(id2) is None
        assert _store_exists(path) is False

    # M6 — accès HTTP par token média inchangé pour un lien partagé.
    def test_m6_media_token_serves_shared_file(self, admin_headers):
        a = _client_headers(admin_headers)
        data = _png(_seed())
        r1 = _upload(a["headers"], f"m6a_{_uid()}.png", data)
        r2 = _upload(a["headers"], f"m6b_{_uid()}.png", data)
        assert r1.status_code == 201 and r2.status_code == 201
        path = _media_row(r1.json()["media_id"])["sftp_path"]
        t = _api("POST", "/api/v1/media-token", headers=a["headers"], json={"path": path})
        assert t.status_code == 200, t.text
        token = t.json()["token"]
        g = _api("GET", f"/media/{path}", params={"token": token})
        assert g.status_code == 200, g.text
        assert g.content == data

    # M7 — la sync (ce que reçoit le player) expose toujours filename = sftp_path.
    def test_m7_sync_payload_filename_unchanged(self, admin_headers):
        a = _client_headers(admin_headers)
        code = a["client"]["user_code"]
        data = _png(_seed())
        r1 = _upload(a["headers"], f"m7a_{_uid()}.png", data)
        r2 = _upload(a["headers"], f"m7b_{_uid()}.png", data)
        m1 = r1.json()["media_id"]
        m2 = r2.json()["media_id"]
        path = _media_row(m1)["sftp_path"]

        site = _api("POST", "/api/v1/sites", headers=admin_headers, json={
            "code": f"SG{_uid()}", "name": f"Site {_uid()}", "is_active": True, "client_code": code,
        })
        assert site.status_code == 201, site.text
        post = _api("POST", "/api/v1/posts", headers=admin_headers, json={
            "site_id": site.json()["site_id"], "code": f"PG{_uid()}", "name": f"Post {_uid()}", "is_active": True,
        })
        assert post.status_code == 201, post.text
        post_id = post.json()["post_id"]

        with _conn() as conn:
            gid = conn.execute(
                "INSERT INTO screen_groups (name) VALUES (%s) RETURNING group_id",
                (f"G30_{_uid()}",),
            ).fetchone()["group_id"]
            conn.execute("INSERT INTO screen_group_posts (group_id, post_id) VALUES (%s, %s)", (gid, post_id))
            conn.execute(
                "INSERT INTO zone_media (post_id, zone_number, media_id, display_order) VALUES (%s, 1, %s, 1)",
                (post_id, m1),
            )
            conn.execute(
                "INSERT INTO zone_media (post_id, zone_number, media_id, display_order) VALUES (%s, 1, %s, 2)",
                (post_id, m2),
            )
        _TEMP_GROUPS.append(gid)

        h = _api("GET", f"/api/v1/groups/{gid}/media-hierarchy", headers=admin_headers)
        assert h.status_code == 200, h.text
        filenames = {item["filename"] for z in h.json()["zones"] for item in z["media"]}
        assert filenames == {path}
        assert _store_exists(path) is True

    # M8 — isolation : un client ne peut ni lire ni signer le média d'un autre.
    def test_m8_cross_client_isolation(self, admin_headers):
        a = _client_headers(admin_headers)
        b = _client_headers(admin_headers)
        ra = _upload(a["headers"], f"m8a_{_uid()}.png", _png(_seed()))
        assert ra.status_code == 201, ra.text
        media_a = ra.json()["media_id"]
        path_a = _media_row(media_a)["sftp_path"]

        assert _api("GET", f"/api/v1/media/{media_a}", headers=b["headers"]).status_code == 404
        t = _api("POST", "/api/v1/media-token", headers=b["headers"], json={"path": path_a})
        assert t.status_code == 403, t.text

    # M9 — migration : dry-run conforme, consolidation, idempotence.
    def test_m9_migration_consolidates_and_is_idempotent(self, admin_headers):
        from app.services.media_maintenance import consolidate, find_duplicate_groups
        from app.services.media_storage import get_media_store

        tag = _uid()
        checksum = f"m30test{tag}".lower()
        data = _png(_seed())
        path_a = f"images/m30_dupA_{tag}.png"
        path_b = f"images/m30_dupB_{tag}.png"

        with get_media_store() as store:
            store.write(path_a, data)
            store.write(path_b, data)

        conn = _conn()
        ids: list[int] = []
        try:
            for path in (path_a, path_b):
                row = conn.execute(
                    """
                    INSERT INTO media (name, original_filename, media_type, mime_type,
                                       file_extension, file_size, sftp_path, checksum,
                                       is_active, client_code)
                    VALUES (%s, %s, 'IMAGE', 'image/png', 'png', %s, %s, %s, TRUE, NULL)
                    RETURNING media_id
                    """,
                    (path.rsplit("/", 1)[-1], path.rsplit("/", 1)[-1], len(data), path, checksum),
                ).fetchone()
                ids.append(row["media_id"])
            conn.commit()

            assert len(find_duplicate_groups(conn, checksum=checksum)) == 1

            with get_media_store() as store:
                dry = consolidate(conn, store, apply=False, checksum=checksum)
                assert dry["groups"] == 1
                assert dry["rows_repointed"] == 0
                n = conn.execute(
                    "SELECT count(DISTINCT sftp_path) AS n FROM media WHERE media_id = ANY(%s)",
                    (ids,),
                ).fetchone()["n"]
                assert n == 2

                stats = consolidate(conn, store, apply=True, checksum=checksum)
                assert stats["rows_repointed"] == 1
                assert stats["files_removed"] == 1

                paths = {
                    r["sftp_path"]
                    for r in conn.execute(
                        "SELECT sftp_path FROM media WHERE media_id = ANY(%s)", (ids,)
                    ).fetchall()
                }
                assert paths == {path_a}
                assert store.exists(path_a) is True
                assert store.exists(path_b) is False

                again = consolidate(conn, store, apply=True, checksum=checksum)
                assert again["groups"] == 0
                assert again["rows_repointed"] == 0
        finally:
            conn.execute("DELETE FROM media WHERE media_id = ANY(%s)", (ids,))
            conn.commit()
            conn.close()
            with get_media_store() as store:
                for p in (path_a, path_b):
                    if store.exists(p):
                        store.remove(p)
