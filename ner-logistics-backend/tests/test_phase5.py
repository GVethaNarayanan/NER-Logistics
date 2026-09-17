import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app, lifespan
from app.database import SessionLocal, engine
from app import models
from app.services.weather_job import fetch_and_store_weather

from tests.conftest import TestSessionLocal

def test_weather_fetch_success(db_session):
    """Test 1, 2, 3: Successful fetch, persistence, data_source='verified'"""
    # Seed a road
    road = models.Road(name="Test Road", start_lat=26.0, start_lon=91.0, end_lat=26.5, end_lon=91.5)
    db_session.add(road)
    db_session.commit()

    mock_data = {
        "current": {
            "precipitation": 12.5,
            "temperature_2m": 25.0,
            "relative_humidity_2m": 80.0,
            "wind_speed_10m": 15.0
        }
    }

    with patch("app.services.weather_job.get_current_and_forecast", return_value=mock_data), \
         patch("app.services.weather_job.SessionLocal", new=TestSessionLocal):
        fetch_and_store_weather()

    snapshots = db_session.query(models.WeatherSnapshot).all()
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.latitude == 26.0
    assert snap.longitude == 91.0
    assert snap.rainfall_mm == 12.5
    assert snap.data_source == "verified"


def test_weather_fetch_api_failure(db_session):
    """Test 5, 6, 14: Timeout/failure handling without crashing."""
    road1 = models.Road(name="Road 1", start_lat=26.0, start_lon=91.0)
    road2 = models.Road(name="Road 2", start_lat=27.0, start_lon=92.0)
    db_session.add_all([road1, road2])
    db_session.commit()

    def mock_fetch(lat, lon):
        if lat == 26.0:
            raise Exception("API Timeout")
        return {"current": {"precipitation": 5.0}}

    with patch("app.services.weather_job.get_current_and_forecast", side_effect=mock_fetch), \
         patch("app.services.weather_job.SessionLocal", new=TestSessionLocal):
        fetch_and_store_weather()

    # Should not crash, and should still process Road 2
    snapshots = db_session.query(models.WeatherSnapshot).all()
    assert len(snapshots) == 1
    assert snapshots[0].latitude == 27.0


def test_auto_risk_fresh_data(client, db_session):
    """Test 8: Fresh auto prediction"""
    road = models.Road(name="Test", start_lat=26.0, start_lon=91.0, status="restricted")
    db_session.add(road)
    db_session.commit()

    bridge = models.Bridge(name="B1", road_id=road.id, condition="poor", latitude=26.0, longitude=91.0)
    db_session.add(bridge)

    snap = models.WeatherSnapshot(latitude=26.0, longitude=91.0, rainfall_mm=50.0, data_source="verified")
    db_session.add(snap)
    db_session.commit()

    resp = client.post("/risk/predict", json={"road_id": road.id})
    assert resp.status_code == 200
    data = resp.json()
    # 50mm rainfall + restricted road + poor bridge -> Medium risk (score ~1.45)
    assert data["risk_level"].upper() == "MEDIUM"
    factors = " ".join(data["factors"])
    assert "stale/fallback" not in factors


def test_auto_risk_stale_fallback(client, db_session):
    """Test 7, 9: Stale data fallback"""
    road = models.Road(name="Test", start_lat=26.0, start_lon=91.0, status="open")
    db_session.add(road)
    db_session.commit()

    # Snapshot from 10 hours ago
    past_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
    snap = models.WeatherSnapshot(latitude=26.0, longitude=91.0, rainfall_mm=0.0, data_source="verified", recorded_at=past_time)
    db_session.add(snap)
    db_session.commit()

    resp = client.post("/risk/predict", json={"road_id": road.id})
    assert resp.status_code == 200
    data = resp.json()
    factors = " ".join(data["factors"])
    assert "Weather data: stale/fallback" in factors


def test_auto_risk_no_data(client, db_session):
    """Test 10: No weather data error"""
    road = models.Road(name="Test", start_lat=26.0, start_lon=91.0)
    db_session.add(road)
    db_session.commit()

    resp = client.post("/risk/predict", json={"road_id": road.id})
    assert resp.status_code == 400
    assert "No verified weather data" in resp.json()["error"]["message"]


def test_manual_risk(client):
    """Test 11: Manual risk prediction backward compatibility"""
    resp = client.post("/risk/predict", json={
        "rainfall_mm": 100,
        "road_condition": "poor",
        "bridge_condition": "poor"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"].upper() == "HIGH"


def test_scheduler_lifecycle():
    """Test 12, 13: Scheduler startup and shutdown"""
    from app.services.weather_job import scheduler
    assert not scheduler.running
    
    with TestClient(app):
        # Lifespan should start the scheduler
        assert scheduler.running
    
    # After client exit, lifespan closes scheduler
    assert not scheduler.running
