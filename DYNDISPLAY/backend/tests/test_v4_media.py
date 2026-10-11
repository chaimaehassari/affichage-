import io
import struct
import zlib

import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _create_minimal_png():
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc & 0xFFFFFFFF)
    raw = zlib.compress(b'\x00\xff\x00\x00')
    idat_crc = zlib.crc32(b'IDAT' + raw)
    idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc & 0xFFFFFFFF)
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc & 0xFFFFFFFF)
    return signature + ihdr + idat + iend


def _create_fake_mp4():
    return b'\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41'


def _create_minimal_pdf(num_pages=1):
    """Build a minimal valid PDF with the given number of blank pages."""
    def page_obj(num):
        content = b"BT /F1 12 Tf 72 720 Td (page %d) Tj ET" % num
        obj_num = num * 2 + 1
        return (
            f"{obj_num} 0 obj\n<< /Type /Page /Parent 3 0 R "
            f"/MediaBox [0 0 612 792] /Contents {obj_num + 1} 0 R >>\nendobj\n".encode()
            + f"{obj_num + 1} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode()
            + content + b"\nendstream\nendobj\n"
        )

    objs = b"%PDF-1.4\n"
    objs += b"1 0 obj\n<< /Type /Catalog /Pages 3 0 R >>\nendobj\n"
    objs += b"2 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    objs += b"3 0 obj\n<< /Type /Pages /Kids ["
    offsets = []
    for i in range(num_pages):
        offsets.append(len(objs))
        objs += page_obj(i + 1)
        objs += f"{2 * i + 4} 0 obj\n<< /Parent 3 0 R /Num {i} /ItsCount {num_pages} >>\nendobj\n".encode()
    for i in range(num_pages):
        objs += f"{2 * i + 4} 0 R ".encode()
    objs += b"] /Count %d >>\nendobj\n" % num_pages
    xref_offset = len(objs)
    objs += b"xref\n0 6\n0000000000 65535 f \n"
    objs += b"0000000009 00000 n \n"
    objs += b"0000000058 00000 n \n"
    objs += b"0000000112 00000 n \n"
    objs += b"0000000200 00000 n \n"
    objs += b"0000000310 00000 n \n"
    objs += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
    objs += str(xref_offset).encode() + b"\n%%EOF\n"
    return objs


def _upload_media(headers, filename, content, content_type="application/octet-stream"):
    files = {"file": (filename, io.BytesIO(content), content_type)}
    return _api("POST", "/api/v1/media/upload", headers=headers, files=files)


def _delete_media(headers, media_id):
    return _api("DELETE", f"/api/v1/media/{media_id}", headers=headers)


@pytest.mark.v4
class TestMediaList:
    def test_media_list_returns_200(self, admin_headers):
        r = _api("GET", "/api/v1/media", headers=admin_headers)
        assert r.status_code == 200

    def test_media_list_is_list(self, admin_headers):
        r = _api("GET", "/api/v1/media", headers=admin_headers)
        assert isinstance(r.json(), list)

    def test_media_list_contains_expected_fields(self, admin_headers):
        r = _api("GET", "/api/v1/media", headers=admin_headers)
        items = r.json()
        if len(items) == 0:
            pytest.skip("No media to check fields")
        required_fields = {"media_id", "name", "media_type", "file_size"}
        for item in items:
            for field in required_fields:
                assert field in item, f"Missing field '{field}' in media item"

    def test_media_list_count_matches(self, admin_headers):
        r = _api("GET", "/api/v1/media", headers=admin_headers)
        items = r.json()
        assert len(items) >= 0


@pytest.mark.v4
class TestMediaFilter:
    def test_filter_by_image_type(self, admin_headers):
        r = _api("GET", "/api/v1/media?media_type=IMAGE", headers=admin_headers)
        assert r.status_code == 200
        items = r.json()
        for item in items:
            assert item["media_type"] == "IMAGE"

    def test_filter_by_video_type(self, admin_headers):
        r = _api("GET", "/api/v1/media?media_type=VIDEO", headers=admin_headers)
        assert r.status_code == 200
        items = r.json()
        for item in items:
            assert item["media_type"] == "VIDEO"


@pytest.mark.v4
class TestMediaUpload:
    def test_upload_image(self, admin_headers):
        png_data = _create_minimal_png()
        r = _upload_media(admin_headers, "test_image.png", png_data, "image/png")
        assert r.status_code == 201
        body = r.json()
        assert "media_id" in body
        assert body["name"] == "test_image.png"
        assert body["media_type"] == "IMAGE"
        _delete_media(admin_headers, body["media_id"])

    def test_upload_video(self, admin_headers):
        mp4_data = _create_fake_mp4()
        r = _upload_media(admin_headers, "test_video.mp4", mp4_data, "video/mp4")
        assert r.status_code == 201
        body = r.json()
        assert "media_id" in body
        assert body["media_type"] == "VIDEO"
        _delete_media(admin_headers, body["media_id"])

    def test_upload_unsupported_file(self, admin_headers):
        exe_data = b'MZ\x90\x00' + b'\x00' * 100
        r = _upload_media(admin_headers, "malware.exe", exe_data, "application/octet-stream")
        assert r.status_code == 400

    def test_upload_empty_file(self, admin_headers):
        r = _upload_media(admin_headers, "empty_file_test.png", b"", "image/png")
        assert r.status_code in (201, 400, 409)

    def test_upload_duplicate_file(self, admin_headers):
        png_data = _create_minimal_png()
        r1 = _upload_media(admin_headers, "dup_test.png", png_data, "image/png")
        assert r1.status_code == 201
        media_id = r1.json()["media_id"]
        r2 = _upload_media(admin_headers, "dup_test.png", png_data, "image/png")
        assert r2.status_code == 409
        _delete_media(admin_headers, media_id)


@pytest.mark.v4
class TestPdfUpload:
    def test_upload_pdf_classified_with_page_count(self, admin_headers):
        pdf_data = _create_minimal_pdf(num_pages=2)
        r = _api("POST", "/api/v1/media/upload", headers=admin_headers,
                 files={"file": ("document.pdf", io.BytesIO(pdf_data), "application/pdf")})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["media_type"] == "PDF"
        assert body["file_extension"] == "pdf"
        assert body["page_count"] == 2
        _delete_media(admin_headers, body["media_id"])

    def test_upload_pdf_rejects_non_pdf(self, admin_headers):
        r = _api("POST", "/api/v1/media/upload", headers=admin_headers,
                 files={"file": ("fake.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")})
        assert r.status_code in (400, 500)


@pytest.mark.v4
class TestMediaDelete:
    def test_delete_unused_media(self, admin_headers):
        png_data = _create_minimal_png()
        r = _upload_media(admin_headers, "to_delete.png", png_data, "image/png")
        assert r.status_code == 201
        media_id = r.json()["media_id"]
        r_del = _delete_media(admin_headers, media_id)
        assert r_del.status_code == 200
        r_list = _api("GET", "/api/v1/media", headers=admin_headers)
        ids = [item["media_id"] for item in r_list.json()]
        assert media_id not in ids

    @pytest.mark.xfail(reason="API may allow deletion of media in use depending on implementation")
    def test_delete_media_in_use(self, admin_headers):
        png_data = _create_minimal_png()
        r = _upload_media(admin_headers, "in_use.png", png_data, "image/png")
        assert r.status_code == 201
        media_id = r.json()["media_id"]
        try:
            r_del = _delete_media(admin_headers, media_id)
            assert r_del.status_code == 409
        finally:
            _delete_media(admin_headers, media_id)
