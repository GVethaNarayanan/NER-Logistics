"""
Phase 11 — Automated Alerts Test Suite

Comprehensive tests for state-transition alert generation, duplicate
prevention, auto-resolution, re-triggering, bridge alerts, ML/Tier1
integration, scheduler behavior, and API compatibility.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app import models
from app.services.alert_job import (
    evaluate_road_alerts,
    evaluate_bridge_alerts,
    evaluate_network_alerts,
    _resolve_alert,
)
from tests.conftest import get_auth_header


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_tables(db: Session):
    """Delete all rows from alert/road/bridge/weather/incident tables."""
    for table in reversed(models.Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def _make_road(db: Session, name="R1", start_lat=26.0, start_lon=91.0,
               end_lat=26.1, end_lon=91.1, status="open") -> models.Road:
    r = models.Road(name=name, start_lat=start_lat, start_lon=start_lon,
                    end_lat=end_lat, end_lon=end_lon, status=status)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_bridge(db: Session, name="B1", road_id=None, condition="good") -> models.Bridge:
    b = models.Bridge(name=name, road_id=road_id, condition=condition,
                      latitude=26.0, longitude=91.0)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _make_weather(db: Session, lat=26.0, lon=91.0, rainfall_mm=0.0,
                  hours_ago=0) -> models.WeatherSnapshot:
    ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_ago)
    w = models.WeatherSnapshot(
        latitude=lat, longitude=lon, rainfall_mm=rainfall_mm,
        data_source="verified", recorded_at=ts,
    )
    db.add(w)
    db.commit()
    return w


def _make_incident(db: Session, road_id, status="reported") -> models.Incident:
    inc = models.Incident(
        road_id=road_id, incident_type="flood", description="test",
        latitude=26.0, longitude=91.0, status=status, severity="high",
    )
    db.add(inc)
    db.commit()
    return inc


def _mock_risk_score(level: str):
    """Return a mock compute_risk_score that always returns the given level."""
    scores = {"LOW": 10.0, "MEDIUM": 50.0, "HIGH": 80.0}
    def mock_fn(**kwargs):
        return {
            "risk_score": scores[level],
            "risk_level": level,
            "factors": ["test"],
            "prediction_source": "tier1_fallback",
        }
    return mock_fn


def _mock_risk_score_ml(level: str):
    """Return a mock compute_risk_score that returns ML-based results."""
    scores = {"LOW": 10.0, "MEDIUM": 50.0, "HIGH": 80.0}
    def mock_fn(**kwargs):
        return {
            "risk_score": scores[level],
            "risk_level": level,
            "factors": ["AI-driven disruption prediction"],
            "prediction_source": "ml",
        }
    return mock_fn


# ════════════════════════════════════════════════════════════════════════════════
# A. ALERT STATE
# ════════════════════════════════════════════════════════════════════════════════

def test_alert_active_state(db_session: Session):
    """Active state is set on new alerts."""
    _clean_tables(db_session)
    a = models.Alert(alert_type="high_risk", message_en="test", status="active")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    assert a.status == "active"
    assert a.resolved_at is None


def test_alert_resolved_state(db_session: Session):
    """Resolved state with timestamp."""
    _clean_tables(db_session)
    a = models.Alert(alert_type="high_risk", message_en="test", status="active")
    db_session.add(a)
    db_session.commit()
    _resolve_alert(a)
    db_session.commit()
    db_session.refresh(a)
    assert a.status == "resolved"
    assert a.resolved_at is not None


# ════════════════════════════════════════════════════════════════════════════════
# B. INITIAL TRANSITION
# ════════════════════════════════════════════════════════════════════════════════

def test_low_to_high_creates_alert(db_session: Session):
    """LOW → HIGH creates exactly one alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 1
    alerts = db_session.query(models.Alert).filter_by(road_id=road.id, status="active").all()
    assert len(alerts) == 1


def test_medium_to_high_creates_alert(db_session: Session):
    """MEDIUM → HIGH creates an alert (no prior active alert exists)."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 1


# ════════════════════════════════════════════════════════════════════════════════
# C. DUPLICATE PREVENTION
# ════════════════════════════════════════════════════════════════════════════════

def test_high_to_high_no_duplicate(db_session: Session):
    """HIGH → HIGH does NOT create another alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        evaluate_road_alerts(db_session)
        db_session.commit()
        # Second evaluation
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 0
    assert stats["suppressed"] == 1
    total = db_session.query(models.Alert).filter_by(road_id=road.id, status="active").count()
    assert total == 1


def test_repeated_evaluation_no_flood(db_session: Session):
    """Multiple repeated evaluations do NOT increase alert count."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        for _ in range(5):
            evaluate_road_alerts(db_session)
            db_session.commit()
    total = db_session.query(models.Alert).filter_by(status="active").count()
    assert total == 1


# ════════════════════════════════════════════════════════════════════════════════
# D. RESOLUTION
# ════════════════════════════════════════════════════════════════════════════════

def test_high_to_medium_resolves(db_session: Session):
    """HIGH → MEDIUM resolves active alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    # Create alert
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    # Resolve
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("MEDIUM")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["resolved"] == 1
    a = db_session.query(models.Alert).filter_by(road_id=road.id).first()
    assert a.status == "resolved"
    assert a.resolved_at is not None


def test_high_to_low_resolves(db_session: Session):
    """HIGH → LOW resolves active alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("LOW")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["resolved"] == 1


def test_resolved_alert_remains_in_db(db_session: Session):
    """Resolved alert persists in the database for audit."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("LOW")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    total = db_session.query(models.Alert).count()
    assert total == 1  # not deleted, just resolved


# ════════════════════════════════════════════════════════════════════════════════
# E. RE-TRIGGER
# ════════════════════════════════════════════════════════════════════════════════

def test_retrigger_after_resolution(db_session: Session):
    """HIGH → LOW (resolves) → HIGH creates a NEW active alert."""
    _clean_tables(db_session)
    _make_road(db_session)
    # Create
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    # Resolve
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("LOW")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    # Re-trigger
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 1
    total = db_session.query(models.Alert).count()
    assert total == 2  # one resolved, one active
    active = db_session.query(models.Alert).filter_by(status="active").count()
    assert active == 1
    resolved = db_session.query(models.Alert).filter_by(status="resolved").count()
    assert resolved == 1


# ════════════════════════════════════════════════════════════════════════════════
# F. BRIDGE CONDITIONS
# ════════════════════════════════════════════════════════════════════════════════

def test_bridge_deterioration_creates_alert(db_session: Session):
    """Bridge condition poor creates alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    bridge = _make_bridge(db_session, road_id=road.id, condition="poor")
    stats = evaluate_bridge_alerts(db_session)
    db_session.commit()
    assert stats["created"] == 1
    a = db_session.query(models.Alert).filter_by(bridge_id=bridge.id, status="active").first()
    assert a is not None
    assert a.alert_type == "bridge_condition"


def test_bridge_unchanged_poor_no_duplicate(db_session: Session):
    """poor → poor does not create duplicate bridge alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    _make_bridge(db_session, road_id=road.id, condition="poor")
    evaluate_bridge_alerts(db_session)
    db_session.commit()
    stats = evaluate_bridge_alerts(db_session)
    db_session.commit()
    assert stats["created"] == 0
    assert stats["suppressed"] == 1


def test_bridge_improvement_resolves(db_session: Session):
    """poor → good resolves active bridge alert."""
    _clean_tables(db_session)
    road = _make_road(db_session)
    bridge = _make_bridge(db_session, road_id=road.id, condition="poor")
    evaluate_bridge_alerts(db_session)
    db_session.commit()
    # Improve condition
    bridge.condition = "good"
    db_session.commit()
    stats = evaluate_bridge_alerts(db_session)
    db_session.commit()
    assert stats["resolved"] == 1
    a = db_session.query(models.Alert).filter_by(bridge_id=bridge.id).first()
    assert a.status == "resolved"


# ════════════════════════════════════════════════════════════════════════════════
# G. ML / TIER 1
# ════════════════════════════════════════════════════════════════════════════════

def test_ml_risk_triggers_alert(db_session: Session):
    """ML prediction (source=ml) can trigger alerts."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score_ml("HIGH")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 1
    a = db_session.query(models.Alert).first()
    assert "source: ml" in a.message_en


def test_tier1_fallback_triggers_alert(db_session: Session):
    """Tier 1 fallback can trigger alerts."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 1
    a = db_session.query(models.Alert).first()
    assert "source: tier1_fallback" in a.message_en


def test_prediction_source_accuracy(db_session: Session):
    """Alert message contains accurate prediction_source."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score_ml("HIGH")):
        evaluate_road_alerts(db_session)
        db_session.commit()
    a = db_session.query(models.Alert).first()
    assert "ml" in a.message_en


# ════════════════════════════════════════════════════════════════════════════════
# H. CONCURRENCY / DUPLICATE SAFETY
# ════════════════════════════════════════════════════════════════════════════════

def test_concurrent_evaluations_no_duplicates(db_session: Session):
    """Simulating two rapid evaluations cannot create duplicate active alerts."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        # First eval
        evaluate_road_alerts(db_session)
        db_session.commit()
        # Second eval immediately (simulating concurrency)
        evaluate_road_alerts(db_session)
        db_session.commit()
    active = db_session.query(models.Alert).filter_by(status="active").count()
    assert active == 1


# ════════════════════════════════════════════════════════════════════════════════
# I. API
# ════════════════════════════════════════════════════════════════════════════════

def test_alert_api_returns_status(client: TestClient, db_session: Session):
    """Alert API response includes status field."""
    _clean_tables(db_session)
    a = models.Alert(alert_type="high_risk", message_en="test", status="active", severity="high")
    db_session.add(a)
    db_session.commit()
    resp = client.get("/alerts/")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "active"


def test_alert_api_filter_by_status(client: TestClient, db_session: Session):
    """Alert API can filter by status."""
    _clean_tables(db_session)
    a1 = models.Alert(alert_type="high_risk", message_en="active one", status="active")
    a2 = models.Alert(alert_type="high_risk", message_en="resolved one", status="resolved",
                      resolved_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add_all([a1, a2])
    db_session.commit()
    # Filter active
    resp = client.get("/alerts/?status=active")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["status"] == "active"
    # Filter resolved
    resp = client.get("/alerts/?status=resolved")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["status"] == "resolved"


def test_alert_api_existing_endpoints_compatible(client: TestClient, db_session: Session):
    """Existing endpoints still work without status filter."""
    _clean_tables(db_session)
    a = models.Alert(alert_type="weather", message_en="storm warning", severity="high", status="active")
    db_session.add(a)
    db_session.commit()
    resp = client.get("/alerts/")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_alert_api_resolved_at_returned(client: TestClient, db_session: Session):
    """resolved_at is returned in API response."""
    _clean_tables(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    a = models.Alert(alert_type="high_risk", message_en="test", status="resolved", resolved_at=now)
    db_session.add(a)
    db_session.commit()
    resp = client.get("/alerts/")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["resolved_at"] is not None


def test_manual_alert_creation_still_works(client: TestClient, db_session: Session, admin_user):
    """Admin manual alert creation preserves backward compatibility."""
    _clean_tables(db_session)
    # Re-create admin user since tables were cleaned
    from app.services.auth_service import create_user
    create_user(db=db_session, username="testadmin", email="admin@test.com",
                plain_password="adminpass123", role="admin")
    headers = get_auth_header(client, "testadmin", "adminpass123")
    resp = client.post("/alerts/", json={
        "alert_type": "delay",
        "message_en": "Manual delay alert",
        "severity": "medium",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["alert_type"] == "delay"
    assert data["status"] == "active"


# ════════════════════════════════════════════════════════════════════════════════
# J. SCHEDULER / BACKGROUND BEHAVIOR
# ════════════════════════════════════════════════════════════════════════════════

def test_evaluate_network_alerts_with_session(db_session: Session):
    """evaluate_network_alerts works with explicit session."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        result = evaluate_network_alerts(db=db_session)
    assert result["road_alerts_created"] == 1


def test_repeated_scheduler_no_flood(db_session: Session):
    """Repeated scheduler executions do not flood the database."""
    _clean_tables(db_session)
    _make_road(db_session)
    _make_bridge(db_session, condition="poor")
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("HIGH")):
        for _ in range(10):
            evaluate_network_alerts(db=db_session)
    road_active = db_session.query(models.Alert).filter_by(
        alert_type="high_risk", status="active").count()
    bridge_active = db_session.query(models.Alert).filter_by(
        alert_type="bridge_condition", status="active").count()
    assert road_active == 1
    assert bridge_active == 1


# ════════════════════════════════════════════════════════════════════════════════
# K. DATABASE / MIGRATION
# ════════════════════════════════════════════════════════════════════════════════

def test_alert_model_has_required_fields(db_session: Session):
    """Alert model has all Phase 11 required fields."""
    _clean_tables(db_session)
    a = models.Alert(
        alert_type="high_risk",
        message_en="test",
        status="active",
        road_id=None,
        bridge_id=None,
        resolved_at=None,
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    assert hasattr(a, "status")
    assert hasattr(a, "resolved_at")
    assert hasattr(a, "bridge_id")


def test_existing_alert_records_preserved(db_session: Session):
    """Legacy alerts (without status) default to 'active'."""
    _clean_tables(db_session)
    # Simulate a legacy alert
    a = models.Alert(alert_type="weather", message_en="legacy alert")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    assert a.status == "active"  # default


# ════════════════════════════════════════════════════════════════════════════════
# ADDITIONAL EDGE CASES
# ════════════════════════════════════════════════════════════════════════════════

def test_no_roads_no_error(db_session: Session):
    """Evaluation with no roads does not error."""
    _clean_tables(db_session)
    stats = evaluate_road_alerts(db_session)
    assert stats["created"] == 0


def test_no_bridges_no_error(db_session: Session):
    """Evaluation with no bridges does not error."""
    _clean_tables(db_session)
    stats = evaluate_bridge_alerts(db_session)
    assert stats["created"] == 0


def test_low_risk_no_alert(db_session: Session):
    """LOW risk does not create an alert."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("LOW")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 0


def test_medium_risk_no_alert(db_session: Session):
    """MEDIUM risk does not create an alert."""
    _clean_tables(db_session)
    _make_road(db_session)
    with patch("app.services.alert_job.compute_risk_score", side_effect=_mock_risk_score("MEDIUM")):
        stats = evaluate_road_alerts(db_session)
        db_session.commit()
    assert stats["created"] == 0


def test_bridge_good_condition_no_alert(db_session: Session):
    """Bridge in good condition does not trigger alert."""
    _clean_tables(db_session)
    _make_bridge(db_session, condition="good")
    stats = evaluate_bridge_alerts(db_session)
    assert stats["created"] == 0


def test_bridge_fair_condition_no_alert(db_session: Session):
    """Bridge in fair condition does not trigger alert."""
    _clean_tables(db_session)
    _make_bridge(db_session, condition="fair")
    stats = evaluate_bridge_alerts(db_session)
    assert stats["created"] == 0
