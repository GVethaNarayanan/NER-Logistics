"""
Phase 4 — Core Infrastructure API Tests

Tests cover:
1.  Road filtering (district, status, combined)
2.  Road pagination (skip, limit, empty page, invalid values)
3.  Road 404 for nonexistent ID
4.  Bridge filtering (road_id, condition)
5.  Bridge pagination
6.  Bridge FK validation (invalid road_id rejected, valid road_id accepted)
7.  Bridge 404 for nonexistent ID
8.  Bridge condition update sets last_verified
9.  District connectivity (correct aggregation, case-insensitive, 404)
10. Incidents pagination
11. Vehicles pagination
12. Alerts pagination
13. Auth regression (public GET, protected write, role restrictions)
"""
from tests.conftest import get_auth_header


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — seed data for Phase 4 tests
# ═══════════════════════════════════════════════════════════════════════════════

def _seed_roads(client, admin_headers, count=5):
    """Seed test roads. Returns list of created road dicts."""
    roads = []
    districts = ["Kamrup", "Kamrup", "Dibrugarh", "Dibrugarh", "Nagaon"]
    statuses = ["open", "open", "blocked", "restricted", "open"]
    for i in range(count):
        r = client.post("/roads/", json={
            "name": f"Test Road {i+1}",
            "road_type": "NH",
            "start_lat": 26.0 + i * 0.1,
            "start_lon": 91.0 + i * 0.1,
            "end_lat": 26.5 + i * 0.1,
            "end_lon": 91.5 + i * 0.1,
            "status": statuses[i % len(statuses)],
            "district": districts[i % len(districts)],
        }, headers=admin_headers)
        assert r.status_code == 200 or r.status_code == 201, f"Failed to seed road {i+1}: {r.text}"
        roads.append(r.json())
    return roads


def _seed_bridges(client, admin_headers, road_ids):
    """Seed test bridges linked to roads. Returns list of created bridge dicts."""
    bridges = []
    conditions = ["good", "fair", "poor", "unverified"]
    for i, road_id in enumerate(road_ids):
        r = client.post("/bridges/", json={
            "name": f"Test Bridge {i+1}",
            "road_id": road_id,
            "latitude": 26.0 + i * 0.05,
            "longitude": 91.0 + i * 0.05,
            "condition": conditions[i % len(conditions)],
        }, headers=admin_headers)
        assert r.status_code == 201, f"Failed to seed bridge {i+1}: {r.text}"
        bridges.append(r.json())
    return bridges


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Road Filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoadFiltering:
    def test_list_roads_returns_paginated(self, client):
        """List endpoint returns paginated structure even with zero roads."""
        resp = client.get("/roads/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    def test_filter_by_district(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        # Roads are public POST for admin - but POST /roads/ has no auth in current implementation
        # Actually POST /roads/ has no auth requirement - it was not protected in Phase 3
        _seed_roads(client, headers)

        resp = client.get("/roads/?district=Kamrup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["district"].lower() == "kamrup"

    def test_filter_by_status(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/?status=blocked")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"].lower() == "blocked"

    def test_filter_district_and_status(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/?district=Kamrup&status=open")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["district"].lower() == "kamrup"
            assert item["status"].lower() == "open"

    def test_filter_case_insensitive(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/?district=kamrup")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

        resp2 = client.get("/roads/?district=KAMRUP")
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 2

    def test_filter_no_results(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/?district=NonExistentDistrict")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Road Pagination
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoadPagination:
    def test_default_pagination(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/")
        data = resp.json()
        assert data["skip"] == 0
        assert data["limit"] == 20  # DEFAULT_PAGE_LIMIT
        assert data["total"] == 5

    def test_custom_skip_limit(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/?skip=2&limit=2")
        data = resp.json()
        assert data["skip"] == 2
        assert data["limit"] == 2
        assert len(data["items"]) == 2
        assert data["total"] == 5

    def test_skip_beyond_total(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/roads/?skip=100")
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 5

    def test_negative_skip_rejected(self, client):
        resp = client.get("/roads/?skip=-1")
        assert resp.status_code == 422

    def test_excessive_limit_capped(self, client):
        resp = client.get("/roads/?limit=999")
        assert resp.status_code == 422

    def test_zero_limit_rejected(self, client):
        resp = client.get("/roads/?limit=0")
        assert resp.status_code == 422

    def test_multiple_pages(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        # Page 1
        p1 = client.get("/roads/?skip=0&limit=2").json()
        # Page 2
        p2 = client.get("/roads/?skip=2&limit=2").json()
        # Page 3
        p3 = client.get("/roads/?skip=4&limit=2").json()

        assert len(p1["items"]) == 2
        assert len(p2["items"]) == 2
        assert len(p3["items"]) == 1  # only 5 roads total

        # No duplicate IDs across pages
        all_ids = [r["id"] for r in p1["items"] + p2["items"] + p3["items"]]
        assert len(all_ids) == len(set(all_ids))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Road 404
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoad404:
    def test_nonexistent_road_returns_404(self, client):
        resp = client.get("/roads/99999")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == 404

    def test_road_create_and_get(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        # Create
        r = client.post("/roads/", json={
            "name": "404 Test Road",
            "start_lat": 26.0,
            "start_lon": 91.0,
            "end_lat": 26.5,
            "end_lon": 91.5,
        }, headers=headers)
        assert r.status_code == 201 or r.status_code == 200
        road_id = r.json()["id"]

        # Get
        r2 = client.get(f"/roads/{road_id}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "404 Test Road"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Bridge Filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestBridgeFiltering:
    def test_list_bridges_paginated(self, client):
        resp = client.get("/bridges/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_filter_by_road_id(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        roads = _seed_roads(client, headers)
        _seed_bridges(client, headers, [roads[0]["id"], roads[0]["id"], roads[1]["id"]])

        resp = client.get(f"/bridges/?road_id={roads[0]['id']}")
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["road_id"] == roads[0]["id"]

    def test_filter_by_condition(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        roads = _seed_roads(client, headers)
        _seed_bridges(client, headers, [roads[0]["id"], roads[1]["id"], roads[2]["id"], roads[3]["id"]])

        resp = client.get("/bridges/?condition=good")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["condition"].lower() == "good"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Bridge FK Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestBridgeFKValidation:
    def test_create_bridge_valid_road_id(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        # Create a road first
        road = client.post("/roads/", json={
            "name": "FK Test Road",
            "start_lat": 26.0, "start_lon": 91.0,
            "end_lat": 26.5, "end_lon": 91.5,
            "district": "Kamrup",
        }, headers=headers).json()

        # Create bridge with valid road_id
        resp = client.post("/bridges/", json={
            "name": "FK Test Bridge",
            "road_id": road["id"],
            "latitude": 26.1,
            "longitude": 91.1,
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["road_id"] == road["id"]

    def test_create_bridge_invalid_road_id(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")

        resp = client.post("/bridges/", json={
            "name": "Invalid FK Bridge",
            "road_id": 99999,
            "latitude": 26.1,
            "longitude": 91.1,
        }, headers=headers)
        assert resp.status_code == 404
        assert "road" in resp.json()["error"]["message"].lower()

    def test_create_bridge_no_road_id(self, client, admin_user):
        """Bridge without road_id should succeed (road_id is nullable)."""
        headers = get_auth_header(client, "testadmin", "adminpass123")

        resp = client.post("/bridges/", json={
            "name": "No Road Bridge",
            "latitude": 26.1,
            "longitude": 91.1,
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["road_id"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Bridge 404 and Condition Update
# ═══════════════════════════════════════════════════════════════════════════════

class TestBridge404AndCondition:
    def test_nonexistent_bridge_returns_404(self, client):
        resp = client.get("/bridges/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == 404

    def test_condition_update_sets_last_verified(self, client, admin_user, field_user):
        admin_headers = get_auth_header(client, "testadmin", "adminpass123")
        field_headers = get_auth_header(client, "testfield", "fieldpass123")

        # Create bridge as admin
        bridge = client.post("/bridges/", json={
            "name": "Condition Test Bridge",
            "latitude": 26.1,
            "longitude": 91.1,
        }, headers=admin_headers).json()
        assert bridge["last_verified"] is None

        # Update condition as field official
        resp = client.patch(
            f"/bridges/{bridge['id']}/condition?condition=good",
            headers=field_headers,
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["condition"] == "good"
        assert updated["last_verified"] is not None

    def test_condition_update_nonexistent_bridge_404(self, client, field_user):
        headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.patch(
            "/bridges/99999/condition?condition=good",
            headers=headers,
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 7. District Connectivity
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistrictConnectivity:
    def test_connectivity_correct_counts(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        roads = _seed_roads(client, headers)
        # Kamrup roads: road[0] (open), road[1] (open) → 2 roads
        # Dibrugarh roads: road[2] (blocked), road[3] (restricted) → 2 roads

        # Add bridges to Kamrup roads
        kamrup_road_ids = [r["id"] for r in roads if r["district"] == "Kamrup"]
        _seed_bridges(client, headers, kamrup_road_ids)

        resp = client.get("/districts/Kamrup/connectivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["district"] == "Kamrup"
        assert data["roads"]["total"] == 2
        assert data["roads"]["open"] == 2
        assert data["roads"]["blocked"] == 0
        assert data["roads"]["restricted"] == 0
        assert data["bridges"]["total"] == 2

    def test_connectivity_case_insensitive(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        r1 = client.get("/districts/kamrup/connectivity")
        r2 = client.get("/districts/KAMRUP/connectivity")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["roads"]["total"] == r2.json()["roads"]["total"]

    def test_connectivity_nonexistent_district_404(self, client):
        resp = client.get("/districts/NonExistentDistrict/connectivity")
        assert resp.status_code == 404

    def test_connectivity_bridge_conditions(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        roads = _seed_roads(client, headers)
        # Dibrugarh has roads[2] (blocked) and roads[3] (restricted)
        dibrugarh_road_ids = [r["id"] for r in roads if r["district"] == "Dibrugarh"]
        _seed_bridges(client, headers, dibrugarh_road_ids)
        # 2 bridges with conditions: good (index 0), fair (index 1)

        resp = client.get("/districts/Dibrugarh/connectivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["roads"]["total"] == 2
        assert data["roads"]["blocked"] == 1
        assert data["roads"]["restricted"] == 1
        assert data["bridges"]["total"] == 2
        assert data["bridges"]["good"] == 1
        assert data["bridges"]["fair"] == 1

    def test_connectivity_district_no_bridges(self, client, admin_user):
        """District with roads but no bridges → bridge counts all zero."""
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)

        resp = client.get("/districts/Nagaon/connectivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["roads"]["total"] == 1
        assert data["bridges"]["total"] == 0
        assert data["bridges"]["good"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Incidents Pagination
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentsPagination:
    def test_list_incidents_paginated(self, client):
        resp = client.get("/incidents/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["skip"] == 0

    def test_incidents_skip_limit(self, client, field_user):
        headers = get_auth_header(client, "testfield", "fieldpass123")
        for i in range(3):
            client.post("/incidents/", json={
                "incident_type": "landslide",
                "latitude": 26.0 + i * 0.1,
                "longitude": 91.0,
            }, headers=headers)

        resp = client.get("/incidents/?skip=1&limit=1")
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Vehicles Pagination
# ═══════════════════════════════════════════════════════════════════════════════

class TestVehiclesPagination:
    def test_list_vehicles_paginated(self, client):
        resp = client.get("/vehicles/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_vehicles_pagination(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        for i in range(3):
            client.post("/vehicles/", json={
                "vehicle_number": f"AS01X{i:04d}",
                "current_lat": 26.0,
                "current_lon": 91.0,
            }, headers=headers)

        resp = client.get("/vehicles/?skip=0&limit=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Alerts Pagination
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsPagination:
    def test_list_alerts_paginated(self, client):
        resp = client.get("/alerts/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_alerts_pagination(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        for i in range(3):
            client.post("/alerts/", json={
                "alert_type": "high_risk",
                "message_en": f"Test alert {i}",
            }, headers=headers)

        resp = client.get("/alerts/?skip=1&limit=1")
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Auth Regression — Phase 3 policies must still hold
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthRegression:
    """Verify that Phase 4 changes did not break Phase 3 auth."""

    def test_public_get_roads_no_auth(self, client):
        resp = client.get("/roads/")
        assert resp.status_code == 200

    def test_public_get_bridges_no_auth(self, client):
        resp = client.get("/bridges/")
        assert resp.status_code == 200

    def test_public_get_incidents_no_auth(self, client):
        resp = client.get("/incidents/")
        assert resp.status_code == 200

    def test_public_get_vehicles_no_auth(self, client):
        resp = client.get("/vehicles/")
        assert resp.status_code == 200

    def test_public_get_alerts_no_auth(self, client):
        resp = client.get("/alerts/")
        assert resp.status_code == 200

    def test_public_risk_predict_no_auth(self, client):
        resp = client.post("/risk/predict", json={
            "rainfall_mm": 50, "road_condition": "fair",
            "bridge_condition": "good", "recent_incidents": 1,
            "terrain_difficulty": 0.3,
        })
        assert resp.status_code == 200

    def test_public_district_connectivity_no_auth(self, client, admin_user):
        """District connectivity must be public."""
        headers = get_auth_header(client, "testadmin", "adminpass123")
        _seed_roads(client, headers)
        resp = client.get("/districts/Kamrup/connectivity")
        assert resp.status_code == 200

    def test_protected_incident_create_no_auth(self, client):
        resp = client.post("/incidents/", json={
            "incident_type": "landslide",
            "latitude": 26.1,
            "longitude": 91.7,
        })
        assert resp.status_code == 401

    def test_protected_bridge_create_no_auth(self, client):
        resp = client.post("/bridges/", json={
            "name": "Unauthorized Bridge",
            "latitude": 26.1,
            "longitude": 91.7,
        })
        assert resp.status_code == 401

    def test_protected_alert_create_no_auth(self, client):
        resp = client.post("/alerts/", json={
            "alert_type": "high_risk",
            "message_en": "No auth",
        })
        assert resp.status_code == 401

    def test_role_restriction_field_cannot_create_bridge(self, client, field_user):
        headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.post("/bridges/", json={
            "name": "Field Bridge",
            "latitude": 26.1,
            "longitude": 91.7,
        }, headers=headers)
        assert resp.status_code == 403

    def test_health_check_public(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
