"""Unit tests for license_utils — must be bit-identical to the Android app."""
import pytest
from unittest.mock import patch

from app.core.license_utils import (
    generate_license,
    validate_license,
    _b32_encode_nopad,
    _b32_decode_nopad,
    LicenseInfo,
)

MOCK_SECRET = "0000000000000000"


def _patched_generate(client_code, sites, posts):
    with patch("app.core.license_utils.get_settings") as mock:
        mock.return_value.LICENSE_SECRET = MOCK_SECRET
        return generate_license(client_code, sites, posts)


def _patched_validate(code):
    with patch("app.core.license_utils.get_settings") as mock:
        mock.return_value.LICENSE_SECRET = MOCK_SECRET
        return validate_license(code)


class TestBase32RoundTrip:
    def test_round_trip_short(self):
        original = b"\x00\x01\x02\x03\x04"
        assert _b32_decode_nopad(_b32_encode_nopad(original)) == original

    def test_round_trip_long(self):
        original = b"Hello, World!"
        assert _b32_decode_nopad(_b32_encode_nopad(original)) == original

    def test_round_trip_empty(self):
        original = b""
        assert _b32_decode_nopad(_b32_encode_nopad(original)) == original


class TestGenerateThenValidate:
    def test_round_trip_succeeds(self):
        code = _patched_generate("ABC12345", 10, 50)
        info = _patched_validate(code)
        assert info is not None
        assert info.client_code == "ABC12345"
        assert info.sites == 10
        assert info.posts == 50

    def test_deterministic(self):
        a = _patched_generate("XYZ99999", 3, 7)
        b = _patched_generate("XYZ99999", 3, 7)
        assert a == b

    def test_format_5char_blocks(self):
        code = _patched_generate("11111111", 5, 5)
        blocks = code.split("-")
        assert len(blocks) > 1
        for block in blocks[:-1]:
            assert len(block) == 5
        assert 1 <= len(blocks[-1]) <= 5


class TestTamperRejection:
    def test_single_char_swap_rejected(self):
        code = _patched_generate("TESTCODE", 1, 1)
        first = code[0]
        replacement = "B" if first == "A" else "A"
        tampered = replacement + code[1:]
        assert _patched_validate(tampered) is None

    def test_truncated_code_rejected(self):
        code = _patched_generate("TESTCODE", 1, 1)
        assert _patched_validate(code[:10]) is None

    def test_garbage_input_rejected(self):
        assert _patched_validate("") is None
        assert _patched_validate("NOT-A-CODE!!") is None
        assert _patched_validate("A1B2") is None


class TestDifferentInputs:
    def test_different_codes_produce_different_licenses(self):
        a = _patched_generate("CODE_A", 1, 1)
        b = _patched_generate("CODE_B", 1, 1)
        assert a != b

    def test_different_sites_produce_different_licenses(self):
        a = _patched_generate("SAME", 1, 1)
        b = _patched_generate("SAME", 2, 1)
        assert a != b

    def test_different_posts_produce_different_licenses(self):
        a = _patched_generate("SAME", 1, 1)
        b = _patched_generate("SAME", 1, 2)
        assert a != b


class TestInteropWithAndroid:
    """Verify that the Python implementation produces codes compatible with the Android app."""

    def test_known_vector(self):
        """Manually construct the expected output for client=12345678, sites=12, posts=34."""
        payload = "12345678:12:34".encode("utf-8")
        import hmac as _hmac
        import hashlib
        mac = _hmac.new(MOCK_SECRET.encode("utf-8"), payload, hashlib.sha256)
        signature = mac.digest()[:8]
        combined = payload + signature
        expected = _b32_encode_nopad(combined)
        expected_formatted = "-".join(expected[i:i + 5] for i in range(0, len(expected), 5))

        produced = _patched_generate("12345678", 12, 34)
        assert produced == expected_formatted
        assert _patched_validate(produced) is not None

    def test_known_vector_real_secret(self):
        """Frozen cross-vector with the REAL deployed secret.

        Expected value generated with the exact same algorithm/inputs by the
        Android app (Kotlin): LicenseManager.generate("TEST01", 5, 20). Uses the
        unpatched LICENSE_SECRET loaded from backend/.env — identical value to
        local.properties -> license.secret on the Android side. Fails if the
        secret is missing or diverges from the deployed one.
        """
        expected = "KRCVG-VBQGE-5DKOR-SGAHR-BLJMK-YIX73-Q"
        produced = generate_license("TEST01", 5, 20)
        assert produced == expected
        info = validate_license(produced)
        assert info is not None
        assert info.client_code == "TEST01"
        assert info.sites == 5
        assert info.posts == 20
