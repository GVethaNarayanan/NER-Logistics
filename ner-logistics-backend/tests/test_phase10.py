import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.services.ml_service import MLService

import pandas as pd
import numpy as np
from app import models
from datetime import datetime, timezone, timedelta

# Create a mock LabelEncoder-like class
class MockLabelEncoder:
    def __init__(self, classes):
        self.classes_ = np.array(classes)
    def transform(self, values):
        return [list(self.classes_).index(v) for v in values]

# Create a mock RandomForest-like class
class MockModel:
    def __init__(self, classes=[0, 1]):
        self.classes_ = np.array(classes)
    
    def predict_proba(self, X):
        # Deterministic mock prediction:
        # High rainfall (>50) -> high disruption prob (0.9)
        # Otherwise -> low disruption prob (0.1)
        res = []
        for _, row in X.iterrows():
            if row.get("rainfall_mm", 0) > 50:
                res.append([0.1, 0.9])
            else:
                res.append([0.9, 0.1])
        return np.array(res)

@pytest.fixture
def mock_ml_service():
    ml = MLService()
    ml.model = MockModel()
    ml.road_encoder = MockLabelEncoder(["fair", "good", "poor"])
    ml.bridge_encoder = MockLabelEncoder(["fair", "good", "poor"])
    ml.is_loaded = True
    ml.disruption_idx = 1
    return ml

@pytest.fixture
def clean_db(db_session: Session):
    for table in reversed(models.Base.metadata.sorted_tables):
        db_session.execute(table.delete())
    db_session.commit()
    return db_session

# Remove client fixture to use conftest client

def test_missing_model_fallback():
    ml = MLService()
    ml.load_model("invalid_path.joblib")
    assert ml.is_loaded is False
    score, source = ml.predict_scalar(100, "good", "good", 0, 0.3)
    assert source == "tier1_fallback"
    assert score is None

def test_corrupt_model_fallback():
    ml = MLService()
    with patch("joblib.load", side_effect=Exception("Corrupt file")):
        ml.load_model("fake.joblib")
    assert ml.is_loaded is False

def test_incompatible_model_fallback():
    ml = MLService()
    # Missing road_encoder
    with patch("joblib.load", return_value={"model": MockModel()}):
        ml.load_model("fake.joblib")
    assert ml.is_loaded is False

def test_verified_class_mapping():
    ml = MLService()
    with patch("joblib.load", return_value={
        "model": MockModel(classes=["not_disrupted", "disrupted"]), 
        "road_encoder": MockLabelEncoder(["good"]), 
        "bridge_encoder": MockLabelEncoder(["good"])
    }):
        # Mock model has no '1', so it should fail to load correctly
        ml.load_model("fake.joblib")
        assert ml.is_loaded is False

def test_predict_proba_mapping(mock_ml_service):
    # Rainfall > 50 -> 0.9 prob -> 90.0 score
    score, source = mock_ml_service.predict_scalar(60.0, "good", "good", 0, 0.3)
    assert source == "ml"
    assert score == 90.0

    # Rainfall <= 50 -> 0.1 prob -> 10.0 score
    score, source = mock_ml_service.predict_scalar(10.0, "good", "good", 0, 0.3)
    assert source == "ml"
    assert score == 10.0

def test_deterministic_prediction(mock_ml_service):
    s1, _ = mock_ml_service.predict_scalar(60.0, "good", "good", 0, 0.3)
    s2, _ = mock_ml_service.predict_scalar(60.0, "good", "good", 0, 0.3)
    assert s1 == s2

def test_unknown_categories_fallback(mock_ml_service):
    # "terrible" is not in ["fair", "good", "poor"]
    score, source = mock_ml_service.predict_scalar(60.0, "terrible", "good", 0, 0.3)
    assert source == "tier1_fallback"
    assert score is None

def test_missing_features(mock_ml_service):
    # Handled by dict.get with defaults
    res = mock_ml_service.predict_bulk([{}])
    assert res[0][1] == "ml"
    assert res[0][0] == 10.0 # Default rainfall is 0 -> 10.0 score

def test_extreme_inputs(mock_ml_service):
    # Handled by max/min clamping
    score, source = mock_ml_service.predict_scalar(-999, "good", "good", 0, -5)
    assert source == "ml"
    assert score == 10.0

def test_bulk_inference(mock_ml_service):
    features = [
        {"rainfall_mm": 60, "road_condition": "good", "bridge_condition": "good", "recent_incidents": 0, "terrain_difficulty": 0.3},
        {"rainfall_mm": 10, "road_condition": "good", "bridge_condition": "good", "recent_incidents": 0, "terrain_difficulty": 0.3},
        {"rainfall_mm": 100, "road_condition": "unknown_cat", "bridge_condition": "good", "recent_incidents": 0, "terrain_difficulty": 0.3}
    ]
    results = mock_ml_service.predict_bulk(features)
    assert len(results) == 3
    assert results[0] == (90.0, "ml")
    assert results[1] == (10.0, "ml")
    assert results[2] == (None, "tier1_fallback")

def test_scalar_bulk_consistency(mock_ml_service):
    s_score, s_src = mock_ml_service.predict_scalar(60, "good", "good", 0, 0.3)
    b_res = mock_ml_service.predict_bulk([{"rainfall_mm": 60, "road_condition": "good", "bridge_condition": "good", "recent_incidents": 0, "terrain_difficulty": 0.3}])
    assert s_score == b_res[0][0]
    assert s_src == b_res[0][1]

def test_risk_predict_endpoint_ml(client: TestClient, mock_ml_service):
    with patch("app.services.risk_engine.ml_service", mock_ml_service):
        response = client.post("/risk/predict", json={
            "rainfall_mm": 60.0,
            "road_condition": "good",
            "bridge_condition": "good",
            "recent_incidents": 0,
            "terrain_difficulty": 0.3
        })
        assert response.status_code == 200
        data = response.json()
        assert data["prediction_source"] == "ml"
        assert data["risk_score"] == 90.0
        assert data["risk_level"] == "HIGH"

def test_risk_predict_endpoint_fallback(client: TestClient):
    # Original ml_service is not loaded (or file missing during test)
    ml = MLService()
    with patch("app.services.risk_engine.ml_service", ml):
        response = client.post("/risk/predict", json={
            "rainfall_mm": 150.0,
            "road_condition": "poor",
            "bridge_condition": "poor",
            "recent_incidents": 2,
            "terrain_difficulty": 1.0
        })
        assert response.status_code == 200
        data = response.json()
        assert data["prediction_source"] == "tier1_fallback"

def _setup_routing_graph(db):
    r1 = models.Road(name="R1", start_lat=0, start_lon=0, end_lat=0, end_lon=1, status="open")
    r2 = models.Road(name="R2", start_lat=0, start_lon=1, end_lat=0, end_lon=2, status="open")
    db.add_all([r1, r2])
    db.commit()
    return r1, r2

def test_ml_powered_safest_routing(client: TestClient, db_session: Session, mock_ml_service, clean_db):
    r1, r2 = _setup_routing_graph(db_session)
    
    # Put high rainfall only on r1 (lat 0, lon 0)
    w = models.WeatherSnapshot(latitude=0, longitude=0, rainfall_mm=100.0, data_source="verified")
    db_session.add(w)
    db_session.commit()
    
    with patch("app.services.ml_service.ml_service", mock_ml_service):
        res = client.post("/routing/route", json={
            "origin_lat": 0, "origin_lon": 0,
            "destination_lat": 0, "destination_lon": 2,
            "preference": "safest"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["properties"]["route_preference"] == "safest"
        # R1 had 100mm rain -> ML prob 0.9 -> score 90.0 -> HIGH level
        assert "average_risk_score" in data["properties"]

def test_shortest_route_backward_compatibility(client: TestClient, db_session: Session, mock_ml_service, clean_db):
    r1, r2 = _setup_routing_graph(db_session)
    
    with patch("app.services.ml_service.ml_service", mock_ml_service):
        res = client.post("/routing/route", json={
            "origin_lat": 0, "origin_lon": 0,
            "destination_lat": 0, "destination_lon": 2,
            "preference": "shortest"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["properties"]["route_preference"] == "shortest"

def test_stale_weather_routing(client: TestClient, db_session: Session, mock_ml_service, clean_db):
    r1, r2 = _setup_routing_graph(db_session)
    w = models.WeatherSnapshot(
        latitude=0, longitude=0, rainfall_mm=100.0, data_source="verified",
        recorded_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
    )
    db_session.add(w)
    db_session.commit()

    with patch("app.services.ml_service.ml_service", mock_ml_service):
        res = client.post("/routing/route", json={
            "origin_lat": 0, "origin_lon": 0,
            "destination_lat": 0, "destination_lon": 2,
            "preference": "safest"
        })
        assert res.status_code == 200
        # If weather is stale, rainfall = 0 -> score 10.0 -> max_risk_score is 10.0
        assert res.json()["properties"]["max_risk_score"] == 10.0
