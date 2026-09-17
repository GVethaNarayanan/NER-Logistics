from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models, schemas
from app.services.risk_engine import compute_risk_score

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/predict", response_model=schemas.RiskOutput)
def predict_risk(payload: schemas.RiskInput, db: Session = Depends(get_db)):
    # MODE B: Automatic if road_id is provided
    if payload.road_id is not None:
        road = db.query(models.Road).filter(models.Road.id == payload.road_id).first()
        if not road:
            raise HTTPException(status_code=404, detail="Road not found")

        # Get road condition based on status
        road_condition = "good"
        if road.status == "blocked":
            road_condition = "poor"
        elif road.status == "restricted":
            road_condition = "fair"

        # Get worst bridge condition
        bridge_conds = db.query(models.Bridge.condition).filter(models.Bridge.road_id == road.id).all()
        bridge_conds = [c[0] for c in bridge_conds]
        if "poor" in bridge_conds:
            bridge_condition = "poor"
        elif "fair" in bridge_conds:
            bridge_condition = "fair"
        else:
            bridge_condition = "good"

        # Stage 5: Use geometry-based weather matching via PostGIS
        from app.services.weather_match import match_weather_for_road
        wmatch = match_weather_for_road(db, road.id)

        # Use effective_rainfall_mm: missing weather applies uncertainty
        # penalty so missing ≠ safe (Correction 4)
        rainfall_mm = wmatch.effective_rainfall_mm

        result = compute_risk_score(
            rainfall_mm=rainfall_mm,
            road_condition=road_condition,
            bridge_condition=bridge_condition,
            recent_incidents=payload.recent_incidents,
            terrain_difficulty=payload.terrain_difficulty,
        )

        # Annotate weather provenance
        result["weather_source"] = wmatch.source
        result["weather_stale"] = wmatch.weather_stale
        result["risk_data_quality"] = wmatch.risk_data_quality
        if wmatch.distance_km >= 0:
            result["weather_distance_km"] = wmatch.distance_km

        # Add weather factors to risk factors list
        if wmatch.risk_factors:
            if isinstance(result.get("factors"), list):
                result["factors"].extend(wmatch.risk_factors)
            
    else:
        # MODE A: Manual
        result = compute_risk_score(
            rainfall_mm=payload.rainfall_mm,
            road_condition=payload.road_condition,
            bridge_condition=payload.bridge_condition,
            recent_incidents=payload.recent_incidents,
            terrain_difficulty=payload.terrain_difficulty,
        )

    db_pred = models.RiskPrediction(
        road_id=payload.road_id,
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        factors=", ".join(result["factors"]),
    )
    db.add(db_pred)
    db.commit()
    return result
