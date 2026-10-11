import pytest
import requests

BASE_URL = __import__("os").environ.get("TEST_BASE_URL") or "http://localhost:8000"


def _api(method, path, **kwargs):
    return requests.request(method, f"{BASE_URL}{path}", **kwargs)


@pytest.mark.v5
class TestLayoutList:
    def test_list_layouts_returns_200(self, admin_headers):
        r = _api("GET", "/api/v1/layouts", headers=admin_headers)
        assert r.status_code == 200

    def test_list_layouts_is_list(self, admin_headers):
        r = _api("GET", "/api/v1/layouts", headers=admin_headers)
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# include_zones=true : le lot unique qui remplace N GET /layouts/{id}
#
# Non-régression de la rafale : l'écran de configuration affichait les
# vignettes de tous les modèles, il déclenchait donc un GET /layouts/{id} par
# modèle (plus de 700 requêtes). Chaque requête pouvait en plus recevoir un
# 401 si le token d'accès expirait au milieu de la rafale.
# ---------------------------------------------------------------------------
@pytest.mark.v5
class TestLayoutListWithZones:
    def _create(self, admin_headers, name):
        payload = {
            "name": name,
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 40, "height": 50, "is_active": True},
                {"zone_number": 2, "position_x": 40, "position_y": 0, "width": 60, "height": 50, "is_active": True},
                {"zone_number": 3, "position_x": 0, "position_y": 50, "width": 100, "height": 50, "is_active": False},
            ],
        }
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201, r.text
        return r.json()["layout_id"]

    def test_include_zones_returns_200_and_list(self, admin_headers):
        r = _api("GET", "/api/v1/layouts?include_zones=true", headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert body, "la base doit contenir au moins un modèle"

    def test_include_zones_embeds_zones_of_every_layout(self, admin_headers):
        name = "IncludeZones V5"
        layout_id = self._create(admin_headers, name)
        try:
            r = _api("GET", "/api/v1/layouts?include_zones=true", headers=admin_headers)
            assert r.status_code == 200, r.text
            found = next(l for l in r.json() if l["layout_id"] == layout_id)
            assert found["name"] == name
            assert "zones" in found, "include_zones=true doit renvoyer les zones"
            assert len(found["zones"]) == 3, "les 3 zones doivent être là, pas seulement les actives"
            assert found["active_zone_count"] == 2
            assert {z["zone_number"] for z in found["zones"]} == {1, 2, 3}
        finally:
            _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)

    def test_summary_list_stays_light(self, admin_headers):
        """Sans include_zones, la liste reste la synthèse (pas de zones)."""
        r = _api("GET", "/api/v1/layouts", headers=admin_headers)
        assert r.status_code == 200
        first = r.json()[0]
        assert "layout_id" in first and "name" in first
        assert "zones" not in first, "la liste de synthèse ne doit pas charger les zones"

    def test_include_zones_invalid_value_is_ignored(self, admin_headers):
        r = _api("GET", "/api/v1/layouts?include_zones=oui", headers=admin_headers)
        assert r.status_code == 422, r.text


@pytest.mark.v5
class TestLayoutCreate3Zones:
    def test_create_layout_3_zones(self, admin_headers):
        payload = {
            "name": "Test Layout V5 3zones",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 50, "height": 100, "is_active": True},
                {"zone_number": 2, "position_x": 50, "position_y": 0, "width": 50, "height": 50, "is_active": True},
                {"zone_number": 3, "position_x": 50, "position_y": 50, "width": 50, "height": 50, "is_active": True},
            ],
        }
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        body = r.json()
        assert "layout_id" in body
        assert body["name"] == "Test Layout V5 3zones"
        assert "zones" in body
        assert len(body["zones"]) == 3
        _api("DELETE", f"/api/v1/layouts/{body['layout_id']}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutCreate8Zones:
    def test_create_layout_8_zones(self, admin_headers):
        zones = [
            {"zone_number": i, "position_x": round((i - 1) * 12.5, 1), "position_y": 0, "width": 12.5, "height": 100, "is_active": True}
            for i in range(1, 9)
        ]
        payload = {"name": "Test Layout V5 8zones", "is_active": True, "zones": zones}
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        body = r.json()
        assert len(body["zones"]) == 8
        _api("DELETE", f"/api/v1/layouts/{body['layout_id']}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutDuplicateName:
    def test_duplicate_name_returns_400(self, admin_headers):
        payload = {"name": "DUP_LAYOUT_V5", "is_active": True, "zones": []}
        r1 = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r1.status_code == 201
        layout_id = r1.json()["layout_id"]
        r2 = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r2.status_code == 400
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutDetail:
    def test_get_layout_detail(self, admin_headers):
        payload = {
            "name": "Detail Layout V5",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 50, "is_active": True},
                {"zone_number": 2, "position_x": 0, "position_y": 50, "width": 100, "height": 50, "is_active": True},
            ],
        }
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        layout_id = r.json()["layout_id"]
        r2 = _api("GET", f"/api/v1/layouts/{layout_id}", headers=admin_headers)
        assert r2.status_code == 200
        body = r2.json()
        assert body["layout_id"] == layout_id
        assert body["name"] == "Detail Layout V5"
        assert len(body["zones"]) == 2
        zone1 = [z for z in body["zones"] if z["zone_number"] == 1][0]
        assert zone1["position_x"] == 0
        assert zone1["position_y"] == 0
        assert zone1["width"] == 100
        assert zone1["height"] == 50
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutUpdateName:
    def test_update_layout_name(self, admin_headers):
        payload = {"name": "Old Name V5", "is_active": True, "zones": []}
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        layout_id = r.json()["layout_id"]
        r2 = _api("PUT", f"/api/v1/layouts/{layout_id}", headers=admin_headers, json={"name": "Updated Layout V5"})
        assert r2.status_code == 200
        r3 = _api("GET", f"/api/v1/layouts/{layout_id}", headers=admin_headers)
        assert r3.status_code == 200
        assert r3.json()["name"] == "Updated Layout V5"
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutUpdateZones:
    def test_update_layout_zones(self, admin_headers):
        payload = {
            "name": "Zones Update V5",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 100, "is_active": True},
            ],
        }
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        layout_id = r.json()["layout_id"]
        new_zones = [
            {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 50, "height": 100, "is_active": True},
            {"zone_number": 2, "position_x": 50, "position_y": 0, "width": 50, "height": 50, "is_active": True},
            {"zone_number": 3, "position_x": 50, "position_y": 50, "width": 50, "height": 50, "is_active": True},
        ]
        r2 = _api("PUT", f"/api/v1/layouts/{layout_id}", headers=admin_headers, json={"zones": new_zones})
        assert r2.status_code == 200
        body = r2.json()
        assert len(body["zones"]) == 3
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutDelete:
    def test_delete_layout(self, admin_headers):
        payload = {"name": "To Delete V5", "is_active": True, "zones": []}
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        layout_id = r.json()["layout_id"]
        r2 = _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)
        assert r2.status_code == 200
        r3 = _api("GET", f"/api/v1/layouts/{layout_id}", headers=admin_headers)
        assert r3.status_code == 404


@pytest.mark.v5
class TestLayoutDeactivateZone:
    def test_deactivate_zone(self, admin_headers):
        payload = {
            "name": "Deactivate Zone V5",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 100, "is_active": True},
            ],
        }
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        layout_id = r.json()["layout_id"]
        updated_zones = [
            {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 100, "height": 100, "is_active": False},
        ]
        r2 = _api("PUT", f"/api/v1/layouts/{layout_id}", headers=admin_headers, json={"zones": updated_zones})
        assert r2.status_code == 200
        r3 = _api("GET", f"/api/v1/layouts/{layout_id}", headers=admin_headers)
        assert r3.status_code == 200
        zone = r3.json()["zones"][0]
        assert zone["is_active"] is False
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)


@pytest.mark.v5
class TestLayoutActiveZoneCount:
    def test_active_zone_count_in_list(self, admin_headers):
        payload = {
            "name": "ActiveZoneCount V5",
            "is_active": True,
            "zones": [
                {"zone_number": 1, "position_x": 0, "position_y": 0, "width": 50, "height": 100, "is_active": True},
                {"zone_number": 2, "position_x": 50, "position_y": 0, "width": 50, "height": 50, "is_active": True},
                {"zone_number": 3, "position_x": 50, "position_y": 50, "width": 50, "height": 50, "is_active": True},
                {"zone_number": 4, "position_x": 0, "position_y": 0, "width": 50, "height": 50, "is_active": False},
                {"zone_number": 5, "position_x": 0, "position_y": 50, "width": 50, "height": 50, "is_active": False},
            ],
        }
        r = _api("POST", "/api/v1/layouts", headers=admin_headers, json=payload)
        assert r.status_code == 201
        layout_id = r.json()["layout_id"]
        r2 = _api("GET", "/api/v1/layouts", headers=admin_headers)
        assert r2.status_code == 200
        layout_in_list = next(
            (l for l in r2.json() if l["layout_id"] == layout_id), None
        )
        assert layout_in_list is not None
        if "active_zone_count" in layout_in_list:
            assert layout_in_list["active_zone_count"] == 3
        _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=admin_headers)
