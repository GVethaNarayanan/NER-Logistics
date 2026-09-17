"""Swagger verification script for Phase 3 auth flow."""
import requests
import json

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("SWAGGER VERIFICATION — Phase 3 Auth Flow")
print("=" * 60)

# 1. Register a field_official user
print("\n1. Register field_official user")
r = requests.post(f"{BASE}/auth/register", json={
    "username": "swagger_field",
    "email": "swagger@test.com",
    "password": "securepass123",
})
print(f"   Status: {r.status_code}")
print(f"   Body: {json.dumps(r.json(), indent=4)}")

# 2. Login
print("\n2. Login as field_official")
r = requests.post(f"{BASE}/auth/login", data={
    "username": "swagger_field",
    "password": "securepass123",
})
print(f"   Status: {r.status_code}")
tokens = r.json()
print(f"   token_type: {tokens['token_type']}")
print(f"   expires_in: {tokens['expires_in']}s")
field_token = tokens["access_token"]

# 3. Protected endpoint with valid auth
print("\n3. Create incident (field_official authorized)")
r = requests.post(f"{BASE}/incidents/", json={
    "incident_type": "landslide",
    "latitude": 26.1,
    "longitude": 91.7,
    "severity": "high",
}, headers={"Authorization": f"Bearer {field_token}"})
print(f"   Status: {r.status_code}")

# 4. Protected endpoint without auth -> 401
print("\n4. Create incident (no auth) -> should be 401")
r = requests.post(f"{BASE}/incidents/", json={
    "incident_type": "flood",
    "latitude": 25.5,
    "longitude": 91.8,
})
print(f"   Status: {r.status_code}")

# 5. Protected endpoint with insufficient role -> 403
print("\n5. Create alert (field_official, admin-only) -> should be 403")
r = requests.post(f"{BASE}/alerts/", json={
    "alert_type": "high_risk",
    "message_en": "Unauthorized attempt",
}, headers={"Authorization": f"Bearer {field_token}"})
print(f"   Status: {r.status_code}")

# 6. Login as admin
print("\n6. Login as admin")
r = requests.post(f"{BASE}/auth/login", data={
    "username": "admin",
    "password": "admin_dev_password",
})
print(f"   Status: {r.status_code}")
admin_token = r.json()["access_token"]

# 7. Admin creates alert (should succeed)
print("\n7. Create alert (admin authorized)")
r = requests.post(f"{BASE}/alerts/", json={
    "alert_type": "high_risk",
    "message_en": "Admin created alert",
}, headers={"Authorization": f"Bearer {admin_token}"})
print(f"   Status: {r.status_code}")

# 8. Public GET endpoints remain accessible
print("\n8. Public GET endpoints (no auth)")
for path in ["/roads/", "/bridges/", "/alerts/", "/vehicles/",
             "/incidents/", "/"]:
    r = requests.get(f"{BASE}{path}")
    print(f"   GET {path}: {r.status_code}")

r = requests.post(f"{BASE}/risk/predict", json={
    "rainfall_mm": 50, "road_condition": "fair",
    "bridge_condition": "good", "recent_incidents": 1,
    "terrain_difficulty": 0.3,
})
print(f"   POST /risk/predict: {r.status_code}")

# 9. Refresh token flow
print("\n9. Refresh token flow")
r = requests.post(f"{BASE}/auth/refresh", json={
    "refresh_token": tokens["refresh_token"],
})
print(f"   Status: {r.status_code}")

# 10. /auth/me
print("\n10. GET /auth/me")
r = requests.get(f"{BASE}/auth/me",
                 headers={"Authorization": f"Bearer {admin_token}"})
print(f"   Status: {r.status_code}")
print(f"   Body: {json.dumps(r.json(), indent=4)}")

# 11. Verify no password hash in any response
print("\n11. Check no password hash leaked")
r = requests.get(f"{BASE}/auth/me",
                 headers={"Authorization": f"Bearer {admin_token}"})
body = json.dumps(r.json())
assert "hashed_password" not in body, "FAIL: password hash leaked!"
assert "$2b$" not in body, "FAIL: bcrypt hash in response!"
print("   PASS: No password hashes in API responses")

print("\n" + "=" * 60)
print("ALL SWAGGER VERIFICATIONS COMPLETE")
print("=" * 60)
