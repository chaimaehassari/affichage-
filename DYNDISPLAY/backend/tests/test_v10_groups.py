import io
import struct
import zlib
import uuid

import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _create_minimal_png(seed=0):
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc & 0xFFFFFFFF)
    b0 = (seed >> 16) & 0xFF
    b1 = (seed >> 8) & 0xFF
    b2 = seed & 0xFF
    raw = zlib.compress(bytes([b0, b1, b2, 0]))
    idat_crc = zlib.crc32(b'IDAT' + raw)
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc & 0xFFFFFFFF)
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


def _unique_seed():
    return int(uuid.uuid4().hex[:8], 16)


# Regle metier : « un site appartient toujours a un client precis ». Ces tests
# creent donc un client jetable par site, supprime en fin de session (apres
# avoir retire les sites puis les postes qui lui sont attaches).
_TEMP_CLIENTS: list[str] = []


def _client_code() -> str:
    import psycopg
    from tests._test_config import get_test_db_url
    code = "V10CL" + _uid()
    conn = psycopg.connect(get_test_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clients (code_client, nom_client, license_sites, license_posts) "
                "VALUES (%s, %s, 10, 50)",
                (code, f"V10 client {code}"),
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
            cur.execute(
                "DELETE FROM posts WHERE site_id IN "
                "(SELECT site_id FROM sites WHERE client_code = ANY(%s))",
                (list(_TEMP_CLIENTS),),
            )
            cur.execute(
                "DELETE FROM sites WHERE client_code = ANY(%s)", (list(_TEMP_CLIENTS),)
            )
            cur.execute(
                "DELETE FROM clients WHERE code_client = ANY(%s)", (list(_TEMP_CLIENTS),)
            )
        conn.commit()
    finally:
        conn.close()
    _TEMP_CLIENTS.clear()


def _create_site(headers, code=None):
    code = code or f"V10_{_uid()}"
    r = _api("POST", "/api/v1/sites", headers=headers, json={
        "code": code, "name": f"Site {code}", "is_active": True,
        "client_code": _client_code(),
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_post(headers, site_id, code=None):
    code = code or f"V10P_{_uid()}"
    r = _api("POST", "/api/v1/posts", headers=headers, json={
        "site_id": site_id, "code": code, "name": f"Post {code}", "is_active": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_layout(headers, name=None):
    r = _api("POST", "/api/v1/layouts", headers=headers, json={
        "name": name or f"Layout V10 {_uid()}", "is_active": True,
        "zones": [
            {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 100, "is_active": True},
        ],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _upload_png(headers, prefix, seed=None):
    seed = seed if seed is not None else _unique_seed()
    fname = f"{prefix}_{_uid()}_{seed}.png"
    r = _api("POST", "/api/v1/media/upload", headers=headers,
             files={"file": (fname, io.BytesIO(_create_minimal_png(seed)), "image/png")})
    assert r.status_code == 201, f"upload {prefix}: {r.status_code} {r.text}"
    return r.json()["media_id"]


def _create_group(headers, name=None):
    final = name or f"Groupe V10 {_uid()}"
    if name:
        final = f"{name}_{_uid()}"
    r = _api("POST", "/api/v1/groups", headers=headers, json={
        "name": final, "description": "test", "is_active": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _cleanup(headers, group_id, media_ids):
    for m in media_ids:
        _api("DELETE", f"/api/v1/media/{m}", headers=headers)


@pytest.mark.v10
class TestV10Groups:

    def _build_world(self, admin_headers):
        """2 sites, 4 posts (2 par site), 1 layout, 1 média."""
        site1 = _create_site(admin_headers)
        site2 = _create_site(admin_headers)
        p1 = _create_post(admin_headers, site1["site_id"])
        p2 = _create_post(admin_headers, site1["site_id"])
        p3 = _create_post(admin_headers, site2["site_id"])
        p4 = _create_post(admin_headers, site2["site_id"])
        outside = _create_post(admin_headers, site2["site_id"])
        layout = _create_layout(admin_headers)
        media = _upload_png(admin_headers, "gfx")
        return {
            "site1": site1, "site2": site2,
            "posts": [p1, p2, p3, p4],
            "outside": outside,
            "layout": layout,
            "media_ids": [media],
            "media": media,
        }

    def test_group_lifecycle_create_compose_modify_remove(self, admin_headers):
        world = self._build_world(admin_headers)
        p1, p2, p3, p4 = world["posts"]
        group = _create_group(admin_headers, "Groupe Casablanca")

        try:
            # Composition initiale vide
            comp = _api("GET", f"/api/v1/groups/{group['group_id']}/composition", headers=admin_headers)
            assert comp.status_code == 200
            data = comp.json()
            assert data["name"].startswith("Groupe Casablanca")
            assert data["post_count"] == 0

            # Ajout des 4 postes (sur 2 sites) via membership idempotente
            mem = _api("PUT", f"/api/v1/groups/{group['group_id']}/membership", headers=admin_headers,
                       json={"post_ids": [p1["post_id"], p2["post_id"], p3["post_id"], p4["post_id"]]})
            assert mem.status_code == 200, mem.text
            data = mem.json()
            assert data["post_count"] == 4
            sites = {s["site_id"]: s for s in data["sites"]}
            # Les 2 sites du groupe sont bien présents dans la composition.
            assert world["site1"]["site_id"] in sites
            assert world["site2"]["site_id"] in sites
            group_member_ids = {
                x["post_id"] for s in data["sites"] for x in s["posts"] if x["in_group"]
            }
            assert group_member_ids == {p["post_id"] for p in world["posts"]}

            # Idempotence : re-ajouter les mêmes postes -> pas de doublon
            mem2 = _api("PUT", f"/api/v1/groups/{group['group_id']}/membership", headers=admin_headers,
                        json={"post_ids": [p1["post_id"], p2["post_id"], p3["post_id"], p4["post_id"]]})
            assert mem2.status_code == 200
            assert mem2.json()["post_count"] == 4

            # Liste des postes du groupe
            gposts = _api("GET", f"/api/v1/groups/{group['group_id']}/posts", headers=admin_headers)
            assert gposts.status_code == 200
            assert len(gposts.json()) == 4

            # Modification du nom
            upd = _api("PUT", f"/api/v1/groups/{group['group_id']}", headers=admin_headers,
                       json={"name": f"Renommé_{_uid()}", "is_active": True})
            assert upd.status_code == 200
            assert upd.json()["name"].startswith("Renommé_")

            # Suppression d'un poste du groupe (p1 retiré)
            rem = _api("PUT", f"/api/v1/groups/{group['group_id']}/membership", headers=admin_headers,
                       json={"post_ids": [p2["post_id"], p3["post_id"], p4["post_id"]]})
            assert rem.status_code == 200
            assert rem.json()["post_count"] == 3
            rposts = rem.json()
            member_ids = {x["post_id"] for s in rposts["sites"] for x in s["posts"] if x["in_group"]}
            assert p1["post_id"] not in member_ids
            assert p2["post_id"] in member_ids
        finally:
            _cleanup(admin_headers, group["group_id"], world["media_ids"])

    def test_apply_config_to_group_all_posts_no_duplicates(self, admin_headers):
        world = self._build_world(admin_headers)
        p1, p2, p3, p4 = world["posts"]
        outside = world["outside"]
        layout = world["layout"]
        media = world["media"]
        group = _create_group(admin_headers, "Groupe Magasin 1")

        try:
            # Construire le groupe des 4 postes
            _api("PUT", f"/api/v1/groups/{group['group_id']}/membership", headers=admin_headers,
                 json={"post_ids": [p["post_id"] for p in world["posts"]]})

            # Appliquer la configuration au groupe (sans sync pour ce test rapide)
            payload = {
                "layout_id": layout["layout_id"],
                "loop_enabled": True,
                "schedule_enabled": False,
                "display_enabled": True,
                "zones": [{"zone_number": 1, "media_id": media, "display_order": 1, "duration_seconds": 10}],
                "sync": False,
            }
            r = _api("POST", f"/api/v1/groups/{group['group_id']}/apply-configuration",
                     headers=admin_headers, json=payload)
            assert r.status_code == 200, r.text
            result = r.json()
            assert result["success_count"] == 4
            assert result["failed_post_ids"] == []

            # Vérifier chaque poste du groupe reçoit la même config
            for post in world["posts"]:
                cfg = _api("GET", f"/api/v1/posts/{post['post_id']}/configuration", headers=admin_headers)
                assert cfg.status_code == 200
                data = cfg.json()
                assert data["layout"]["layout_id"] == layout["layout_id"]
                assert data["loop_enabled"] is True
                z = data["zones"][0]
                assert z["media_playlist"][0]["media_id"] == media

            # Aucun poste extérieur au groupe ne reçoit la config
            outside_cfg = _api("GET", f"/api/v1/posts/{outside['post_id']}/configuration", headers=admin_headers)
            assert outside_cfg.status_code == 200
            odata = outside_cfg.json()
            assert odata["layout"] is None or odata["layout"].get("layout_id") != layout["layout_id"]
        finally:
            _cleanup(admin_headers, group["group_id"], world["media_ids"])

    def test_apply_config_syncs_all_group_posts(self, admin_headers):
        world = self._build_world(admin_headers)
        layout = world["layout"]
        media = world["media"]
        group = _create_group(admin_headers, "Groupe Tous les écrans")

        try:
            _api("PUT", f"/api/v1/groups/{group['group_id']}/membership", headers=admin_headers,
                 json={"post_ids": [p["post_id"] for p in world["posts"]]})

            payload = {
                "layout_id": layout["layout_id"],
                "loop_enabled": True,
                "schedule_enabled": False,
                "display_enabled": True,
                "zones": [{"zone_number": 1, "media_id": media, "display_order": 1, "duration_seconds": 10}],
                "sync": True,
            }
            r = _api("POST", f"/api/v1/groups/{group['group_id']}/apply-configuration",
                     headers=admin_headers, json=payload)
            assert r.status_code == 200, r.text
            result = r.json()
            assert result["success_count"] == 4
            assert len(result["synced_post_ids"]) == 4
            assert sorted(result["synced_post_ids"]) == sorted(p["post_id"] for p in world["posts"])
        finally:
            _cleanup(admin_headers, group["group_id"], world["media_ids"])

    def test_delete_group(self, admin_headers):
        world = self._build_world(admin_headers)
        group = _create_group(admin_headers, "Groupe à supprimer")
        try:
            _api("PUT", f"/api/v1/groups/{group['group_id']}/membership", headers=admin_headers,
                 json={"post_ids": [world["posts"][0]["post_id"]]})
            r = _api("DELETE", f"/api/v1/groups/{group['group_id']}", headers=admin_headers)
            assert r.status_code == 200
            # Groupe devenu introuvable
            g = _api("GET", f"/api/v1/groups/{group['group_id']}", headers=admin_headers)
            assert g.status_code == 404
        finally:
            _cleanup(admin_headers, group["group_id"], world["media_ids"])