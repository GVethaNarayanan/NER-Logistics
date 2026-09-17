"""Phase 4 Swagger/integration verification script."""
import requests
import json

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("PHASE 4 — Swagger Verification")
print("=" * 60)

# Login as admin
admin_resp = requests.post(f"{BASE}/auth/login", data={
    "username": "admin",
    "password": "admin_dev_password",
})
assert admin_resp.status_code == 200
admin_token = admin_resp.json()["access_token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}

# 1. Create test roads
print("\n1. Seeding roads")
road_ids = []
for i, (district, status) in enumerate([
    ("Kamrup", "open"), ("Kamrup", "blocked"),
    ("Dibrugarh", "open"), ("Dibrugarh", "restricted"),
    ("Nagaon", "open"),
]):
    r = requests.post(f"{BASE}/roads/", json={
        "name": f"Test Road {i+1}",
        "road_type": "NH",
        "start_lat": 26.0 + i * 0.1, "start_lon": 91.0,
        "end_lat": 26.5 + i * 0.1, "end_lon": 91.5,
        "status": status, "district": district,
    })
    assert r.status_code == 200, f"Failed: {r.text}"
    road_ids.append(r.json()["id"])
    print(f"   Road {i+1}: id={road_ids[-1]}, district={district}, status={status}")

# 2. Road filtering
print("\n2. Road filtering")
r = requests.get(f"{BASE}/roads/?district=Kamrup")
data = r.json()
print(f"   district=Kamrup: total={data['total']}, items={len(data['items'])}")
assert data["total"] == 2

r = requests.get(f"{BASE}/roads/?status=open")
data = r.json()
print(f"   status=open: total={data['total']}")
assert data["total"] == 3

r = requests.get(f"{BASE}/roads/?district=Kamrup&status=open")
data = r.json()
print(f"   district=Kamrup&status=open: total={data['total']}")
assert data["total"] == 1

# 3. Road pagination
print("\n3. Road pagination")
r = requests.get(f"{BASE}/roads/?skip=2&limit=2")
data = r.json()
print(f"   skip=2&limit=2: items={len(data['items'])}, total={data['total']}, skip={data['skip']}, limit={data['limit']}")
assert len(data["items"]) == 2
assert data["total"] == 5

# 4. Road 404
print("\n4. Road 404")
r = requests.get(f"{BASE}/roads/99999")
print(f"   GET /roads/99999: status={r.status_code}")
assert r.status_code == 404

# 5. Create bridges with FK validation
print("\n5. Bridge FK validation")
r = requests.post(f"{BASE}/bridges/", json={
    "name": "Valid Bridge",
    "road_id": road_ids[0],
    "latitude": 26.1, "longitude": 91.1,
    "condition": "good",
}, headers=admin_headers)
print(f"   Valid road_id={road_ids[0]}: status={r.status_code}")
assert r.status_code == 201

r = requests.post(f"{BASE}/bridges/", json={
    "name": "Invalid Bridge",
    "road_id": 99999,
    "latitude": 26.1, "longitude": 91.1,
}, headers=admin_headers)
print(f"   Invalid road_id=99999: status={r.status_code}")
assert r.status_code == 404

# Create more bridges for aggregation test
for i, road_id in enumerate(road_ids[:4]):
    cond = ["good", "fair", "poor", "unverified"][i]
    requests.post(f"{BASE}/bridges/", json={
        "name": f"Bridge {i+2}",
        "road_id": road_id,
        "latitude": 26.0 + i * 0.05, "longitude": 91.0 + i * 0.05,
        "condition": cond,
    }, headers=admin_headers)

# 6. Bridge filtering
print("\n6. Bridge filtering")
r = requests.get(f"{BASE}/bridges/?condition=good")
data = r.json()
print(f"   condition=good: total={data['total']}")
assert data["total"] >= 1

# 7. Bridge condition update + last_verified
print("\n7. Bridge condition update")
bridges = requests.get(f"{BASE}/bridges/").json()["items"]
bridge_id = bridges[0]["id"]
r = requests.patch(
    f"{BASE}/bridges/{bridge_id}/condition?condition=poor",
    headers=admin_headers,
)
assert r.status_code == 200
updated = r.json()
print(f"   Bridge {bridge_id}: condition={updated['condition']}, last_verified={updated['last_verified']}")
assert updated["condition"] == "poor"
assert updated["last_verified"] is not None

# 8. District connectivity
print("\n8. District connectivity")
for district in ["Kamrup", "Dibrugarh", "Nagaon"]:
    r = requests.get(f"{BASE}/districts/{district}/connectivity")
    assert r.status_code == 200
    data = r.json()
    print(f"   {district}: roads={data['roads']}, bridges={data['bridges']}")

r = requests.get(f"{BASE}/districts/NonExistent/connectivity")
print(f"   NonExistent: status={r.status_code}")
assert r.status_code == 404

# 9. Case-insensitive district matching
print("\n9. Case-insensitive district")
r1 = requests.get(f"{BASE}/districts/kamrup/connectivity")
r2 = requests.get(f"{BASE}/districts/KAMRUP/connectivity")
assert r1.status_code == 200 and r2.status_code == 200
assert r1.json()["roads"]["total"] == r2.json()["roads"]["total"]
print("   kamrup == KAMRUP: OK")

# 10. Pagination on all endpoints
print("\n10. Pagination across all endpoints")
for endpoint in ["/roads/", "/bridges/", "/incidents/", "/vehicles/", "/alerts/"]:
    r = requests.get(f"{BASE}{endpoint}")
    data = r.json()
    assert "items" in data and "total" in data and "skip" in data and "limit" in data
    print(f"   {endpoint}: total={data['total']}, structure OK")

# 11. Public access preserved
print("\n11. Public GET access (no auth)")
for path in ["/roads/", "/bridges/", "/incidents/", "/vehicles/", "/alerts/",
             "/districts/Kamrup/connectivity", "/"]:
    r = requests.get(f"{BASE}{path}")
    assert r.status_code == 200, f"FAIL: {path} returned {r.status_code}"
    print(f"   GET {path}: {r.status_code}")

# 12. Protected write still requires auth
print("\n12. Protected write endpoints (no auth)")
for path, body in [
    ("/bridges/", {"name": "X", "latitude": 26, "longitude": 91}),
    ("/incidents/", {"incident_type": "test", "latitude": 26, "longitude": 91}),
    ("/alerts/", {"alert_type": "test", "message_en": "test"}),
]:
    r = requests.post(f"{BASE}{path}", json=body)
    assert r.status_code == 401, f"FAIL: POST {path} should be 401, got {r.status_code}"
    print(f"   POST {path}: {r.status_code} (correctly protected)")

# 13. OpenAPI schema check
print("\n13. OpenAPI schema endpoints")
r = requests.get(f"{BASE}/openapi.json")
assert r.status_code == 200
openapi = r.json()
paths = list(openapi["paths"].keys())
expected = ["/roads/", "/bridges/", "/districts/{district_name}/connectivity"]
for ep in expected:
    assert ep in paths, f"Missing endpoint: {ep}"
    print(f"   {ep}: present in OpenAPI schema")

print("\n" + "=" * 60)
print("ALL PHASE 4 VERIFICATIONS PASSED")
print("=" * 60)
