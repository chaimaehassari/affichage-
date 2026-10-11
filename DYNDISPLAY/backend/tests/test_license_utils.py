"""Unit tests for license_utils — règle du code client (T2F)."""
import pytest

from app.core.license_utils import (
    CLIENT_CODE_MAX_LENGTH,
    normalize_client_code,
)


class TestClientCodeRule:
    """Règle du code client — doit rester alignée sur l'app Android
    « Licence T2F » : lettres + chiffres, 8 caractères maximum."""

    def test_max_length_matches_android_app(self):
        assert CLIENT_CODE_MAX_LENGTH == 8

    @pytest.mark.parametrize("raw,expected", [
        ("ABC123", "ABC123"),
        ("T2F2026", "T2F2026"),
        ("CLT001A", "CLT001A"),
        ("12345678", "12345678"),
        ("A1", "A1"),
    ])
    def test_accepts_alphanumeric(self, raw, expected):
        assert normalize_client_code(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("abc123", "ABC123"),
        ("clt001a", "CLT001A"),
        ("  abc123  ", "ABC123"),
    ])
    def test_trims_and_uppercases(self, raw, expected):
        assert normalize_client_code(raw) == expected

    @pytest.mark.parametrize("raw", ["ABC12345X", "T2F2026XY", "ABCDEFGHI"])
    def test_rejects_more_than_8_characters(self, raw):
        assert normalize_client_code(raw) is None

    @pytest.mark.parametrize("raw", ["ABC-123", "ABC 123", "ABC_123", "ABC.1", "ABCÉ12"])
    def test_rejects_non_alphanumeric(self, raw):
        assert normalize_client_code(raw) is None

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_rejects_empty(self, raw):
        assert normalize_client_code(raw) is None