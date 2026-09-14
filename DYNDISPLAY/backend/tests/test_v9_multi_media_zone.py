import io
import struct
import zlib
import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"


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
    pixel = bytes([b0, b1, b2, 0])
    raw = zlib.compress(pixel)
    idat_crc = zlib.crc32(b'IDAT' + raw)
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc & 0xFFFFFFFF)
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


def _unique_seed():
    return int(uuid.uuid4().hex[:8], 16)


def _create_site(headers):
    code = f"S9_{_uid()}"
    r = _api("POST", "/api/v1/sites", headers=headers, json={
        "code": code, "name": f"Site {code}", "is_active": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_post(headers, site_id):
    code = f"P9_{_uid()}"
    r = _api("POST", "/api/v1/posts", headers=headers, json={
        "site_id": site_id, "code": code, "name": f"Post {code}", "is_active": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_layout(headers):
    r = _api("POST", "/api/v1/layouts", headers=headers, json={
        "name": f"Layout V9 {_uid()}", "is_active": True,
        "zones": [
            {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 50, "height": 100, "is_active": True},
            {"zone_number": 2, "position_x": 50, "position_y": 0, "width": 50, "height": 100, "is_active": True},
        ],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _upload_png(headers, prefix, seed=0):
    fname = f"{prefix}_{_uid()}_{seed}.png"
    r = _api("POST", "/api/v1/media/upload", headers=headers,
             files={"file": (fname, io.BytesIO(_create_minimal_png(seed)), "image/png")})
    assert r.status_code == 201, f"upload {prefix}: {r.status_code} {r.text}"
    return r.json()["media_id"]


def _cleanup(headers, site_id, post_id, media_ids):
    for m in media_ids:
        _api("DELETE", f"/api/v1/media/{m}", headers=headers)
    if post_id:
        _api("DELETE", f"/api/v1/posts/{post_id}", headers=headers)
    _api("DELETE", f"/api/v1/sites/{site_id}", headers=headers)


def _set_config(headers, post_id, layout_id, zone_entries, loop_enabled=True):
    """zone_entries = {zone_number: [media_id, ...]}. Envoie une entrée par média avec display_order."""
    zones = []
    for zone_number, media_ids in zone_entries.items():
        if not media_ids:
            zones.append({"zone_number": zone_number, "media_id": None})
            continue
        for idx, mid in enumerate(media_ids, start=1):
            zones.append({
                "zone_number": zone_number,
                "media_id": mid,
                "display_order": idx,
                "duration_seconds": 10 if len(media_ids) > 0 else None,
            })
    r = _api("PUT", f"/api/v1/posts/{post_id}/configuration", headers=headers, json={
        "layout_id": layout_id,
        "loop_enabled": loop_enabled,
        "schedule_enabled": False,
        "display_enabled": True,
        "zones": zones,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _preview(headers, post_id):
    r = _api("GET", f"/api/v1/posts/{post_id}/config-preview", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.v9
class TestV9MultiMediaZone:
    def _setup(self, admin_headers):
        site = _create_site(admin_headers)
        post = _create_post(admin_headers, site["site_id"])
        layout = _create_layout(admin_headers)
        m1 = _upload_png(admin_headers, "m_a", _unique_seed())
        m2 = _upload_png(admin_headers, "m_b", _unique_seed())
        m3 = _upload_png(admin_headers, "m_c", _unique_seed())
        return site, post, layout, [m1, m2, m3]

    def test_zone_with_one_media(self, admin_headers):
        site, post, layout, [m1, m2, m3] = self._setup(admin_headers)
        try:
            _set_config(admin_headers, post["post_id"], layout["layout_id"],
                        {1: [m1], 2: []})
            preview = _preview(admin_headers, post["post_id"])
            zones = {z["zone_number"]: z for z in preview["zones"]}
            assert set(zones.keys()) == {1}
            plist = zones[1]["media_playlist"]
            assert len(plist) == 1
            assert plist[0]["media_id"] == m1
        finally:
            _cleanup(admin_headers, site["site_id"], post["post_id"], [m1, m2, m3])

    def test_zone_with_two_media_preserves_order(self, admin_headers):
        site, post, layout, [m1, m2, m3] = self._setup(admin_headers)
        try:
            _set_config(admin_headers, post["post_id"], layout["layout_id"],
                        {1: [m2, m1]})
            preview = _preview(admin_headers, post["post_id"])
            zones = {z["zone_number"]: z for z in preview["zones"]}
            plist = zones[1]["media_playlist"]
            assert [p["media_id"] for p in plist] == [m2, m1]
        finally:
            _cleanup(admin_headers, site["site_id"], post["post_id"], [m1, m2, m3])

    def test_zone_with_multiple_media_no_duplicates(self, admin_headers):
        site, post, layout, [m1, m2, m3] = self._setup(admin_headers)
        try:
            _set_config(admin_headers, post["post_id"], layout["layout_id"],
                        {1: [m1, m2, m3]})
            preview = _preview(admin_headers, post["post_id"])
            zones = {z["zone_number"]: z for z in preview["zones"]}
            # Une seule entrée de zone, pas une par média.
            assert len([z for z in preview["zones"] if z["zone_number"] == 1]) == 1
            plist = zones[1]["media_playlist"]
            ids = [p["media_id"] for p in plist]
            assert ids == [m1, m2, m3]
            assert len(ids) == len(set(ids)), "doublons détectés dans la playlist"
        finally:
            _cleanup(admin_headers, site["site_id"], post["post_id"], [m1, m2, m3])

    def test_multiple_zones_each_multiple_media(self, admin_headers):
        site, post, layout, [m1, m2, m3] = self._setup(admin_headers)
        try:
            _set_config(admin_headers, post["post_id"], layout["layout_id"],
                        {1: [m1, m2], 2: [m3, m1]})
            preview = _preview(admin_headers, post["post_id"])
            by_zone = {}
            for z in preview["zones"]:
                assert z["zone_number"] not in by_zone, "zone dupliquée dans le config"
                by_zone[z["zone_number"]] = z
            assert set(by_zone.keys()) == {1, 2}
            assert [p["media_id"] for p in by_zone[1]["media_playlist"]] == [m1, m2]
            assert [p["media_id"] for p in by_zone[2]["media_playlist"]] == [m3, m1]
        finally:
            _cleanup(admin_headers, site["site_id"], post["post_id"], [m1, m2, m3])

    def test_durations_preserved_per_media(self, admin_headers):
        site, post, layout, [m1, m2, m3] = self._setup(admin_headers)
        try:
            _set_config(admin_headers, post["post_id"], layout["layout_id"],
                        {1: [m1, m2, m3]})
            preview = _preview(admin_headers, post["post_id"])
            zones = {z["zone_number"]: z for z in preview["zones"]}
            for p in zones[1]["media_playlist"]:
                assert "duration_seconds" in p
                assert "filename" in p
                assert "media_id" in p
                assert "media_type" in p
        finally:
            _cleanup(admin_headers, site["site_id"], post["post_id"], [m1, m2, m3])

    def test_loop_flag_present(self, admin_headers):
        site, post, layout, [m1, m2, m3] = self._setup(admin_headers)
        try:
            _set_config(admin_headers, post["post_id"], layout["layout_id"],
                        {1: [m1, m2, m3]}, loop_enabled=True)
            preview = _preview(admin_headers, post["post_id"])
            assert preview.get("loop_enabled") is True
            zones = {z["zone_number"]: z for z in preview["zones"]}
            for z in zones.values():
                # loop implicite via loop_enabled au niveau du poste
                assert "media_playlist" in z
        finally:
            _cleanup(admin_headers, site["site_id"], post["post_id"], [m1, m2, m3])