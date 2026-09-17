"""
Phase 3 — Authentication & Authorization Tests

Tests cover:
1.  Successful registration
2.  Duplicate registration rejection
3.  Successful login
4.  Invalid login rejection
5.  Access token validation (/auth/me)
6.  Refresh token flow
7.  Protected endpoint without authentication (401)
8.  Protected endpoint with valid authentication (200)
9.  Role restriction (field_official cannot admin-only)
10. Admin access to admin-only endpoints
11. Field-official access to field-level endpoints
12. Public GET endpoints remain accessible without auth
"""
from tests.conftest import get_auth_header


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Registration
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegistration:
    def test_register_success(self, client):
        resp = client.post("/auth/register", json={
            "username": "newuser",
            "email": "new@test.com",
            "password": "securepass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@test.com"
        assert data["role"] == "field_official"
        assert "hashed_password" not in data
        assert "password" not in data

    def test_register_duplicate_username(self, client, field_user):
        resp = client.post("/auth/register", json={
            "username": "testfield",  # same as field_user fixture
            "email": "different@test.com",
            "password": "securepass123",
        })
        assert resp.status_code == 409
        assert "already registered" in resp.json()["error"]["message"].lower() or \
               "already registered" in str(resp.json()).lower()

    def test_register_duplicate_email(self, client, field_user):
        resp = client.post("/auth/register", json={
            "username": "differentuser",
            "email": "field@test.com",  # same as field_user fixture
            "password": "securepass123",
        })
        assert resp.status_code == 409

    def test_register_cannot_self_assign_admin(self, client):
        resp = client.post("/auth/register", json={
            "username": "sneakyuser",
            "email": "sneaky@test.com",
            "password": "securepass123",
            "role": "admin",
        })
        assert resp.status_code == 422  # validation error

    def test_register_short_password(self, client):
        resp = client.post("/auth/register", json={
            "username": "shortpw",
            "email": "short@test.com",
            "password": "abc",
        })
        assert resp.status_code == 422

    def test_register_short_username(self, client):
        resp = client.post("/auth/register", json={
            "username": "ab",
            "email": "short@test.com",
            "password": "securepass123",
        })
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Login
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogin:
    def test_login_success(self, client, field_user):
        resp = client.post("/auth/login", data={
            "username": "testfield",
            "password": "fieldpass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_wrong_password(self, client, field_user):
        resp = client.post("/auth/login", data={
            "username": "testfield",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401
        # Must NOT reveal what was wrong
        err_msg = str(resp.json())
        assert "password" not in err_msg.lower() or "invalid credentials" in err_msg.lower()

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", data={
            "username": "doesnotexist",
            "password": "somepassword",
        })
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Token validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenValidation:
    def test_me_with_valid_token(self, client, field_user):
        headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testfield"
        assert data["role"] == "field_official"
        assert "hashed_password" not in data

    def test_me_without_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client):
        resp = client.get("/auth/me", headers={
            "Authorization": "Bearer invalid.token.here"
        })
        assert resp.status_code == 401

    def test_me_with_malformed_header(self, client):
        resp = client.get("/auth/me", headers={
            "Authorization": "NotBearer sometoken"
        })
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Refresh token flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestRefreshToken:
    def test_refresh_success(self, client, field_user):
        # Login first
        login_resp = client.post("/auth/login", data={
            "username": "testfield",
            "password": "fieldpass123",
        })
        refresh_token = login_resp.json()["refresh_token"]

        # Refresh
        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["expires_in"] > 0

    def test_refresh_with_invalid_token(self, client):
        resp = client.post("/auth/refresh", json={
            "refresh_token": "invalid.token.here",
        })
        assert resp.status_code == 401

    def test_refresh_with_access_token_rejected(self, client, field_user):
        """Access tokens should not be accepted as refresh tokens."""
        login_resp = client.post("/auth/login", data={
            "username": "testfield",
            "password": "fieldpass123",
        })
        access_token = login_resp.json()["access_token"]

        resp = client.post("/auth/refresh", json={
            "refresh_token": access_token,
        })
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Protected endpoints — no auth → 401
# ═══════════════════════════════════════════════════════════════════════════════

class TestProtectedWithoutAuth:
    def test_create_incident_no_auth(self, client):
        resp = client.post("/incidents/", json={
            "incident_type": "landslide",
            "latitude": 26.1,
            "longitude": 91.7,
        })
        assert resp.status_code == 401

    def test_update_bridge_condition_no_auth(self, client):
        resp = client.patch("/bridges/1/condition?condition=good")
        assert resp.status_code == 401

    def test_create_alert_no_auth(self, client):
        resp = client.post("/alerts/", json={
            "alert_type": "high_risk",
            "message_en": "Test alert",
        })
        assert resp.status_code == 401

    def test_update_vehicle_location_no_auth(self, client):
        resp = client.patch("/vehicles/1/location?lat=26.0&lon=91.0")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Protected endpoints — with valid auth
# ═══════════════════════════════════════════════════════════════════════════════

class TestProtectedWithAuth:
    def test_field_official_create_incident(self, client, field_user):
        headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.post("/incidents/", json={
            "incident_type": "landslide",
            "latitude": 26.1,
            "longitude": 91.7,
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["incident_type"] == "landslide"

    def test_admin_create_alert(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        resp = client.post("/alerts/", json={
            "alert_type": "high_risk",
            "message_en": "Test alert from admin",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["alert_type"] == "high_risk"

    def test_admin_create_bridge(self, client, admin_user):
        headers = get_auth_header(client, "testadmin", "adminpass123")
        resp = client.post("/bridges/", json={
            "name": "Test Bridge",
            "latitude": 26.1,
            "longitude": 91.7,
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["name"] == "Test Bridge"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Role restrictions
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoleRestrictions:
    def test_field_official_cannot_create_alert(self, client, field_user):
        """Alert creation is admin-only."""
        headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.post("/alerts/", json={
            "alert_type": "high_risk",
            "message_en": "Sneaky alert",
        }, headers=headers)
        assert resp.status_code == 403

    def test_field_official_cannot_create_bridge(self, client, field_user):
        """Bridge creation is admin-only."""
        headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.post("/bridges/", json={
            "name": "Unauthorized Bridge",
            "latitude": 26.1,
            "longitude": 91.7,
        }, headers=headers)
        assert resp.status_code == 403

    def test_field_official_can_update_bridge_condition(self, client, field_user, admin_user):
        """Bridge condition update is field_official or admin."""
        # First create a bridge as admin
        admin_headers = get_auth_header(client, "testadmin", "adminpass123")
        create_resp = client.post("/bridges/", json={
            "name": "Condition Bridge",
            "latitude": 26.1,
            "longitude": 91.7,
        }, headers=admin_headers)
        assert create_resp.status_code == 201
        bridge_id = create_resp.json()["id"]

        # Field official updates condition
        field_headers = get_auth_header(client, "testfield", "fieldpass123")
        resp = client.patch(
            f"/bridges/{bridge_id}/condition?condition=good",
            headers=field_headers,
        )
        assert resp.status_code == 200

    def test_admin_has_full_access(self, client, admin_user):
        """Admin can do everything field_official can and more."""
        headers = get_auth_header(client, "testadmin", "adminpass123")

        # Admin can create incident (field_official or admin)
        resp = client.post("/incidents/", json={
            "incident_type": "flood",
            "latitude": 25.5,
            "longitude": 91.8,
        }, headers=headers)
        assert resp.status_code == 200

        # Admin can create alert (admin-only)
        resp = client.post("/alerts/", json={
            "alert_type": "weather",
            "message_en": "Admin alert",
        }, headers=headers)
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Public GET endpoints remain accessible without auth
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicEndpointsRemainPublic:
    """CRITICAL: These tests verify that GIS dashboard read access is not broken."""

    def test_get_roads_public(self, client):
        resp = client.get("/roads/")
        assert resp.status_code == 200

    def test_get_roads_by_id_public(self, client):
        # Phase 4 fixed this: now returns proper 404 instead of 500.
        resp = client.get("/roads/999")
        assert resp.status_code == 404, "Non-existent road should return 404"
        assert resp.status_code not in (401, 403), \
            "Public GET endpoint must not require authentication"

    def test_get_bridges_public(self, client):
        resp = client.get("/bridges/")
        assert resp.status_code == 200

    def test_get_incidents_public(self, client):
        resp = client.get("/incidents/")
        assert resp.status_code == 200

    def test_get_vehicles_public(self, client):
        resp = client.get("/vehicles/")
        assert resp.status_code == 200

    def test_get_alerts_public(self, client):
        resp = client.get("/alerts/")
        assert resp.status_code == 200

    def test_risk_predict_public(self, client):
        resp = client.post("/risk/predict", json={
            "rainfall_mm": 50,
            "road_condition": "fair",
            "bridge_condition": "good",
            "recent_incidents": 1,
            "terrain_difficulty": 0.3,
        })
        assert resp.status_code == 200

    def test_health_check_public(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
