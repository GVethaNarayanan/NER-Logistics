import pytest
from app import models, schemas
from sqlalchemy import text

def test_backfill_verification(db_session):
    # Verify no non-legacy roads are missing endpoints if geometry is not null
    count = db_session.execute(text("SELECT COUNT(*) FROM roads WHERE geometry IS NOT NULL AND start_lat IS NULL")).scalar()
    assert count == 0

def test_legacy_preservation(db_session):
    # Verify legacy roads are intact (should be 80)
    count = db_session.execute(text("SELECT COUNT(*) FROM roads WHERE is_legacy = true")).scalar()
    assert count == 80

def test_bbox_filtering(client):
    resp = client.get("/roads/bbox?min_lon=90&min_lat=25&max_lon=93&max_lat=28&zoom=12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert "total_matched" in data

def test_bbox_limit(client):
    resp = client.get("/roads/bbox?min_lon=90&min_lat=25&max_lon=93&max_lat=28&zoom=12&limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["features"]) <= 5

def test_zoom_simplification(client):
    # zoom < 8 should return 0 features
    resp = client.get("/roads/bbox?min_lon=90&min_lat=25&max_lon=93&max_lat=28&zoom=7")
    assert resp.status_code == 200
    assert len(resp.json()["features"]) == 0

def test_connectivity_by_district_id(client, db_session):
    # Find a valid district ID first
    district = db_session.execute(text("SELECT id, name FROM districts LIMIT 1")).fetchone()
    if district:
        resp = client.get(f"/districts/{district.id}/connectivity")
        assert resp.status_code in (200, 404) # 404 if no roads exist

def test_point_to_district(client):
    # Valid point in Assam
    resp = client.get("/districts/locate?lat=26.14&lon=91.73")
    assert resp.status_code == 200
    data = resp.json()
    assert data["district_id"] is not None

def test_district_boundary(client, db_session):
    district = db_session.execute(text("SELECT id FROM districts WHERE boundary IS NOT NULL LIMIT 1")).fetchone()
    if district:
        resp = client.get(f"/districts/{district.id}/boundary")
        assert resp.status_code == 200
        assert resp.json()["type"] == "Feature"
