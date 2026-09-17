import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from app.main import app
from app import models
from tests.conftest import get_auth_header

def test_create_incident_status_ignored(client, db_session, admin_user):
    """Test that a newly created incident is always 'reported', even if 'status' is provided in JSON."""
    auth = get_auth_header(client, "testadmin", "adminpass123")
    road = models.Road(name="Road1", start_lat=26.0, start_lon=91.0)
    db_session.add(road)
    db_session.commit()

    resp = client.post("/incidents/", headers=auth, json={
        "incident_type": "flood",
        "latitude": 26.0,
        "longitude": 91.0,
        "road_id": road.id,
        "status": "resolved"  # Should be ignored
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "reported"
    assert data["synced"] == "synced"


def test_geo_validation(client, db_session, admin_user):
    auth = get_auth_header(client, "testadmin", "adminpass123")
    # Invalid latitude
    resp = client.post("/incidents/", headers=auth, json={
        "incident_type": "flood",
        "latitude": 91.0, # > 90
        "longitude": 91.0
    })
    assert resp.status_code == 422
    
    # Invalid longitude
    resp = client.post("/incidents/", headers=auth, json={
        "incident_type": "flood",
        "latitude": 90.0,
        "longitude": 181.0 # > 180
    })
    assert resp.status_code == 422


def test_status_lifecycle_transitions(client, db_session, admin_user):
    auth = get_auth_header(client, "testadmin", "adminpass123")
    inc = models.Incident(incident_type="flood", latitude=26.0, longitude=91.0, status="reported")
    db_session.add(inc)
    db_session.commit()

    # Invalid: reported -> resolved
    resp = client.patch(f"/incidents/{inc.id}/status", headers=auth, json={"status": "resolved"})
    assert resp.status_code == 400
    
    # Valid: reported -> verified
    resp = client.patch(f"/incidents/{inc.id}/status", headers=auth, json={"status": "verified"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"

    # Invalid: verified -> reported
    resp = client.patch(f"/incidents/{inc.id}/status", headers=auth, json={"status": "reported"})
    assert resp.status_code == 400

    # Valid: verified -> resolved
    resp = client.patch(f"/incidents/{inc.id}/status", headers=auth, json={"status": "resolved"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    # Invalid: resolved -> verified
    resp = client.patch(f"/incidents/{inc.id}/status", headers=auth, json={"status": "verified"})
    assert resp.status_code == 400


def test_auth_on_status_transition(client, db_session):
    inc = models.Incident(incident_type="flood", latitude=26.0, longitude=91.0, status="reported")
    db_session.add(inc)
    db_session.commit()

    # Unauthenticated
    resp = client.patch(f"/incidents/{inc.id}/status", json={"status": "verified"})
    assert resp.status_code == 401


def test_batch_sync_mixed_validity(client, db_session, admin_user):
    auth = get_auth_header(client, "testadmin", "adminpass123")
    road = models.Road(name="Road1", start_lat=26.0, start_lon=91.0)
    db_session.add(road)
    db_session.commit()

    payload = [
        {"incident_type": "flood", "latitude": 26.0, "longitude": 91.0}, # Valid
        {"incident_type": "landslide", "latitude": 26.0, "longitude": 91.0, "road_id": 999}, # Invalid Road ID
        {"incident_type": "accident", "latitude": 26.0, "longitude": 91.0, "road_id": road.id} # Valid
    ]

    resp = client.post("/incidents/sync-batch", headers=auth, json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["successful_ids"]) == 2
    assert len(data["failed_indexes"]) == 1
    assert data["failed_indexes"][0]["index"] == 1
    assert "Road 999 not found" in data["failed_indexes"][0]["error"]

    # Verify successful records are synced
    incidents = db_session.query(models.Incident).all()
    assert len(incidents) == 2
    for inc in incidents:
        assert inc.synced == "synced"
        assert inc.status == "reported"


def test_batch_sync_auth(client):
    # Unauthenticated
    resp = client.post("/incidents/sync-batch", json=[])
    assert resp.status_code == 401


def test_filtering(client, db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    inc1 = models.Incident(incident_type="flood", severity="high", status="reported", latitude=26.0, longitude=91.0, road_id=1, reported_at=now - timedelta(days=2))
    inc2 = models.Incident(incident_type="landslide", severity="medium", status="verified", latitude=26.0, longitude=91.0, road_id=1, reported_at=now)
    inc3 = models.Incident(incident_type="flood", severity="high", status="verified", latitude=26.0, longitude=91.0, road_id=2, reported_at=now)
    db_session.add_all([inc1, inc2, inc3])
    db_session.commit()

    # road_id
    assert len(client.get("/incidents/?road_id=1").json()["items"]) == 2
    
    # severity + status
    assert len(client.get("/incidents/?severity=high&status=verified").json()["items"]) == 1

    # dates
    start_date = (now - timedelta(days=1)).isoformat()
    assert len(client.get(f"/incidents/?start_date={start_date}").json()["items"]) == 2
    
    end_date = (now - timedelta(days=1)).isoformat()
    assert len(client.get(f"/incidents/?end_date={end_date}").json()["items"]) == 1


def test_photo_upload(client, db_session, admin_user):
    auth = get_auth_header(client, "testadmin", "adminpass123")
    inc = models.Incident(incident_type="flood", latitude=26.0, longitude=91.0)
    db_session.add(inc)
    db_session.commit()

    file_content = b"fake image content"
    files = {"file": ("test.jpg", file_content, "image/jpeg")}
    
    resp = client.post(f"/incidents/{inc.id}/photo", headers=auth, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "/media/incident" in data["photo_url"]
    assert data["photo_url"].endswith(".jpg")

    # Reject non-image
    files_invalid = {"file": ("test.txt", b"text", "text/plain")}
    resp_invalid = client.post(f"/incidents/{inc.id}/photo", headers=auth, files=files_invalid)
    assert resp_invalid.status_code == 400
