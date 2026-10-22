"""
Phase 11 — Automated Alert Generation Service

State-transition alert engine that:
- Evaluates all roads and bridges for alert-worthy conditions
- Creates alerts ONLY on genuine state transitions (e.g. LOW → HIGH)
- Suppresses duplicates when state is unchanged (HIGH → HIGH)
- Auto-resolves alerts when conditions improve (HIGH → LOW)
- Persists all state in the database for restart safety

Uses existing Phase 10 Tier 2 ML / Tier 1 risk pipeline.
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models
from app.services.risk_engine import compute_risk_score, compute_bulk_risk_scores
from app.database import SessionLocal

logger = logging.getLogger("ner_logistics.alert_job")

# ── Risk level that triggers an alert ─────────────────────────────────────────
ALERT_RISK_LEVELS = {"HIGH"}

# ── Bridge condition that triggers an alert ───────────────────────────────────
ALERT_BRIDGE_CONDITIONS = {"poor"}


def _get_active_road_alerts(db: Session) -> dict:
    """Return a dict mapping road_id -> active Alert for high_risk alerts."""
    active = db.query(models.Alert).filter(
        and_(
            models.Alert.alert_type == "high_risk",
            models.Alert.status == "active",
            models.Alert.road_id.isnot(None),
        )
    ).all()
    return {a.road_id: a for a in active}


def _get_active_bridge_alerts(db: Session) -> dict:
    """Return a dict mapping bridge_id -> active Alert for bridge_condition alerts."""
    active = db.query(models.Alert).filter(
        and_(
            models.Alert.alert_type == "bridge_condition",
            models.Alert.status == "active",
            models.Alert.bridge_id.isnot(None),
        )
    ).all()
    return {a.bridge_id: a for a in active}


def _resolve_alert(alert: models.Alert) -> None:
    """Mark an alert as resolved with a timestamp."""
    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)


def evaluate_road_alerts(db: Session) -> dict:
    """
    Evaluate roads for alert-worthy risk levels using batch PostGIS weather matching.

    Stage 5 changes:
    - Uses batch_match_weather_for_roads() for one-shot spatial weather lookup
    - Enforces 50km weather distance cap (Correction 2)
    - Missing weather = degraded confidence, NOT safe (Correction 4)
    - Does NOT auto-resolve alerts when weather data is missing
    - Preserves all state-transition logic (suppress/create/resolve)

    Returns summary dict: {created: int, resolved: int, suppressed: int}
    """
    from app.services.weather_match import (
        batch_match_weather_for_roads,
        _make_missing_result,
    )
    import time

    stats = {"created": 0, "resolved": 0, "suppressed": 0, "evaluated": 0}

    # Fetch roads that are open and have geometry (non-legacy)
    roads = db.query(models.Road).filter(
        models.Road.status == "open",
        models.Road.geometry.isnot(None),
        models.Road.is_legacy == False,
    ).all()

    if not roads:
        return stats

    road_ids = [r.id for r in roads]
    road_map = {r.id: r for r in roads}

    active_alerts = _get_active_road_alerts(db)

    # ── Batch weather matching (one PostGIS query, 50km cap) ──────────────
    t0 = time.time()
    weather_results = batch_match_weather_for_roads(db, road_ids=None)
    weather_time = time.time() - t0
    logger.info(
        "Batch weather matching: %d roads matched in %.2fs",
        len(weather_results), weather_time
    )

    # Bulk fetch unresolved incidents
    unresolved_incidents = db.query(models.Incident).filter(
        models.Incident.status.in_(["reported", "verified"])
    ).all()
    incidents_by_road = {}
    for inc in unresolved_incidents:
        if inc.road_id:
            incidents_by_road[inc.road_id] = incidents_by_road.get(inc.road_id, 0) + 1

    # Bulk fetch bridges
    bridges = db.query(models.Bridge).all()
    bridges_by_road = {}
    for b in bridges:
        if b.road_id:
            bridges_by_road.setdefault(b.road_id, []).append(b)

    # First pass: gather all features for bulk ML prediction
    features_list = []
    for road in roads:
        wmatch = weather_results.get(road.id, _make_missing_result())
        rainfall_mm = wmatch.effective_rainfall_mm

        bridge_condition = "good"
        road_bridges = bridges_by_road.get(road.id, [])
        bridge_conds = [b.condition for b in road_bridges]
        if "poor" in bridge_conds:
            bridge_condition = "poor"
        elif "fair" in bridge_conds:
            bridge_condition = "fair"

        recent_incidents = incidents_by_road.get(road.id, 0)
        
        features_list.append({
            "rainfall_mm": rainfall_mm,
            "road_condition": getattr(road, "condition", "fair"),
            "bridge_condition": bridge_condition,
            "recent_incidents": recent_incidents,
            "terrain_difficulty": getattr(road, "terrain_difficulty", 0.3)
        })

    # Bulk compute all risk scores at once (vectorized ML prediction)
    bulk_results = compute_bulk_risk_scores(features_list)

    # Second pass: evaluate alerts based on computed scores
    for road, risk_output in zip(roads, bulk_results):
        wmatch = weather_results.get(road.id, _make_missing_result())
        risk_level = risk_output["risk_level"]
        risk_score = risk_output["risk_score"]
        prediction_source = risk_output.get("prediction_source", "tier1_fallback")

        # Add weather provenance factors
        if wmatch.is_missing:
            risk_output.setdefault("factors", [])
            if isinstance(risk_output["factors"], list):
                risk_output["factors"].extend(wmatch.risk_factors)

        existing_alert = active_alerts.get(road.id)
        stats["evaluated"] += 1

        if risk_level in ALERT_RISK_LEVELS:
            if existing_alert:
                # HIGH → HIGH: suppress duplicate
                stats["suppressed"] += 1
                logger.debug("Suppressed duplicate alert for road_id=%d (still %s)", road.id, risk_level)
            else:
                # LOW/MEDIUM → HIGH: create new alert
                source_note = f"source: {prediction_source}"
                if wmatch.is_missing:
                    source_note += ", weather: missing"
                elif wmatch.weather_stale:
                    source_note += ", weather: stale"

                new_alert = models.Alert(
                    alert_type="high_risk",
                    message_en=f"High risk detected on road '{road.name}' (score: {risk_score}, {source_note})",
                    road_id=road.id,
                    severity="high",
                    status="active",
                )
                db.add(new_alert)
                stats["created"] += 1
                logger.info("Created alert for road_id=%d risk_level=%s score=%.1f source=%s",
                            road.id, risk_level, risk_score, prediction_source)
        else:
            if existing_alert:
                # Only auto-resolve if we have verified weather data.
                # Do NOT auto-resolve when weather is missing (Correction 4).
                if wmatch.source == "verified":
                    _resolve_alert(existing_alert)
                    stats["resolved"] += 1
                    logger.info("Auto-resolved alert id=%d for road_id=%d (now %s, weather verified)",
                                existing_alert.id, road.id, risk_level)
                else:
                    # Keep alert active when weather is missing/stale
                    stats["suppressed"] += 1
                    logger.debug(
                        "Kept alert active for road_id=%d (risk=%s but weather=%s)",
                        road.id, risk_level, wmatch.source
                    )

    return stats


def evaluate_bridge_alerts(db: Session) -> dict:
    """
    Evaluate all bridges for alert-worthy condition deterioration.

    Returns summary dict: {created: int, resolved: int, suppressed: int}
    """
    stats = {"created": 0, "resolved": 0, "suppressed": 0}

    bridges = db.query(models.Bridge).all()
    if not bridges:
        return stats

    active_alerts = _get_active_bridge_alerts(db)

    for bridge in bridges:
        condition = getattr(bridge, "condition", "good")
        existing_alert = active_alerts.get(bridge.id)

        if condition in ALERT_BRIDGE_CONDITIONS:
            if existing_alert:
                # poor → poor: suppress duplicate
                stats["suppressed"] += 1
                logger.debug("Suppressed duplicate bridge alert for bridge_id=%d", bridge.id)
            else:
                # good/fair → poor: create alert
                new_alert = models.Alert(
                    alert_type="bridge_condition",
                    message_en=f"Bridge '{bridge.name}' condition deteriorated to '{condition}'",
                    bridge_id=bridge.id,
                    severity="high",
                    status="active",
                )
                db.add(new_alert)
                stats["created"] += 1
                logger.info("Created bridge alert for bridge_id=%d condition=%s", bridge.id, condition)
        else:
            if existing_alert:
                # poor → good/fair: auto-resolve
                _resolve_alert(existing_alert)
                stats["resolved"] += 1
                logger.info("Auto-resolved bridge alert id=%d for bridge_id=%d (now %s)",
                            existing_alert.id, bridge.id, condition)

    return stats


def evaluate_network_alerts(db: Session = None) -> dict:
    """
    Main entry point for the background alert evaluation job.

    Evaluates all roads and bridges, applies state-transition logic,
    and commits all changes in a single transaction.

    Can be called with an explicit db session (for testing) or
    will create its own session (for background scheduler use).
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        road_stats = evaluate_road_alerts(db)
        bridge_stats = evaluate_bridge_alerts(db)
        db.commit()

        total = {
            "road_alerts_created": road_stats["created"],
            "road_alerts_resolved": road_stats["resolved"],
            "road_alerts_suppressed": road_stats["suppressed"],
            "bridge_alerts_created": bridge_stats["created"],
            "bridge_alerts_resolved": bridge_stats["resolved"],
            "bridge_alerts_suppressed": bridge_stats["suppressed"],
        }

        created = road_stats["created"] + bridge_stats["created"]
        resolved = road_stats["resolved"] + bridge_stats["resolved"]
        suppressed = road_stats["suppressed"] + bridge_stats["suppressed"]

        if created or resolved:
            logger.info("Alert evaluation complete: created=%d resolved=%d suppressed=%d",
                        created, resolved, suppressed)
        else:
            logger.debug("Alert evaluation complete: no state transitions detected (suppressed=%d)", suppressed)

        return total
    except Exception as e:
        db.rollback()
        logger.error("Alert evaluation failed: %s", str(e))
        raise
    finally:
        if own_session:
            db.close()
