"""Tests de sécurité des TOKENS MÉDIA (GET /media/{path} + POST /api/v1/media-token).

Garanties vérifiées :
  - un token média a une durée de vie bornée (MEDIA_TOKEN_EXPIRE_MINUTES) ;
  - un token média EXPIRÉ est rejeté (401/403) ;
  - un token média est SCOPÉ à un seul fichier : un token pour `a.png` ne
    donne pas accès à `b.png` (403) ;
  - le token de SESSION (typ=access) n'est jamais accepté sur /media :
    il ne circule pas dans les URL (401) ;
  - un token média valide et scopé passe le contrôle d'accès (le 404
    « fichier introuvable » prouve que la requête a franchi la porte).
"""

import datetime
from datetime import timezone

import jwt
import pytest
import requests

from app.core.config import get_settings
from app.core.security import create_media_token

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


def _mint(headers, path):
    return _api("POST", "/api/v1/media-token", headers=headers, json={"path": path})


def _expired_media_token(path, user_id="1"):
    payload = {
        "sub": str(user_id),
        "typ": "media",
        "media_path": path,
        "exp": datetime.datetime(2020, 1, 1, tzinfo=timezone.utc),
    }
    opts = get_settings()
    return jwt.encode(payload, opts.JWT_SECRET_KEY, algorithm=opts.JWT_ALGORITHM)


@pytest.mark.v20
class TestMediaTokenMint:
    def test_mint_requires_auth(self):
        r = _mint({}, "images/logo.png")
        assert r.status_code in (401, 403)

    def test_mint_returns_scoped_short_lived_token(self, admin_headers):
        r = _mint(admin_headers, "images/logo.png")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token"]
        assert body["media_path"] == "images/logo.png"
        opts = get_settings()
        assert body["expires_in"] == opts.MEDIA_TOKEN_EXPIRE_MINUTES * 60

        payload = jwt.decode(body["token"], opts.JWT_SECRET_KEY, algorithms=[opts.JWT_ALGORITHM])
        assert payload["typ"] == "media"
        assert payload["media_path"] == "images/logo.png"
        # Durée de vie bornée : exp <= now + MEDIA_TOKEN_EXPIRE_MINUTES
        import time
        assert payload["exp"] - int(time.time()) <= opts.MEDIA_TOKEN_EXPIRE_MINUTES * 60

    def test_mint_rejects_missing_path(self, admin_headers):
        assert _mint(admin_headers, "").status_code == 422
        assert _mint(admin_headers, "   ").status_code == 422


@pytest.mark.v20
class TestMediaTokenGate:
    def test_expired_media_token_rejected(self, admin_headers):
        expired = _expired_media_token("images/logo.png")
        r = _api("GET", f"/media/images/logo.png?token={expired}")
        assert r.status_code in (401, 403)

    def test_access_token_rejected_on_media_route(self, admin_token):
        # Le token de session ne doit JAMAIS être accepté sur /media
        # (s'il l'était, le token de session circulerait dans les URL/logs).
        r = _api("GET", f"/media/images/logo.png?token={admin_token}")
        assert r.status_code == 401

    def test_media_token_scoped_to_one_media(self, admin_headers):
        token_a = _mint(admin_headers, "images/a.png").json()["token"]
        # Token émis pour images/a.png -> refusé sur images/b.png
        r = _api("GET", f"/media/images/b.png?token={token_a}")
        assert r.status_code == 403

    def test_valid_scoped_token_passes_gate(self, admin_headers):
        token = _mint(admin_headers, "images/a.png").json()["token"]
        # Fichier inexistant -> 404 : prouve que le token SCOPÉ est accepté
        # (la porte d'accès est franchie, seul le fichier manque).
        r = _api("GET", f"/media/images/a.png?token={token}")
        assert r.status_code == 404

    def test_bearer_media_token_accepted(self, admin_headers):
        token = _mint(admin_headers, "images/a.png").json()["token"]
        r = _api("GET", "/media/images/a.png", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_media_token_not_usable_as_session(self, admin_headers):
        # Un token média volé ne doit pas pouvoir être utilisé sur l'API.
        token = _mint(admin_headers, "images/a.png").json()["token"]
        r = _api("GET", "/api/v1/media", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    def test_create_media_token_unit(self):
        # Vérification unitaire directe : scoping + TTL + typ.
        from app.core.security import decode_media_token
        token = create_media_token(1, "videos/spot.mp4")
        payload = decode_media_token(token)
        assert payload is not None
        assert payload["typ"] == "media"
        assert payload["media_path"] == "videos/spot.mp4"
        assert payload["sub"] == "1"
        assert decode_media_token(
            _expired_media_token("videos/spot.mp4")
        ) is None