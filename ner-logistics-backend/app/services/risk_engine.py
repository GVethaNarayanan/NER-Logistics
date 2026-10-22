"""
Tier 1 risk engine: a transparent, weighted rule-based scorer.

No training data required -- this is the guaranteed-to-work baseline from
ML_DESIGN.md that ships on day one. ml/train_model.py adds the Tier 2
learned classifier on top of this once real historical events are compiled
(see data/historical_disruptions.csv.example).
"""

from app.services.ml_service import ml_service

CONDITION_SCORE = {"good": 0.0, "fair": 0.5, "poor": 1.0, "unverified": 0.6}

WEIGHTS = {
    "rainfall": 30,
    "road_condition": 20,
    "bridge_condition": 20,
    "recent_incidents": 20,
    "terrain_difficulty": 10,
}


def compute_risk_score(
    rainfall_mm: float,
    road_condition: str,
    bridge_condition: str,
    recent_incidents: int,
    terrain_difficulty: float,
) -> dict:
    # Attempt ML inference first
    ml_score, source = ml_service.predict_scalar(
        rainfall_mm, road_condition, bridge_condition, recent_incidents, terrain_difficulty
    )

    if source == "ml" and ml_score is not None:
        score = ml_score
        if score < 35:
            level = "LOW"
        elif score < 65:
            level = "MEDIUM"
        else:
            level = "HIGH"
        return {
            "risk_score": score, 
            "risk_level": level, 
            "factors": ["AI-driven disruption prediction"],
            "prediction_source": "ml"
        }

    # Tier 1 Fallback
    rainfall_component = min(rainfall_mm / 100.0, 1.0) * WEIGHTS["rainfall"]
    road_component = CONDITION_SCORE.get(road_condition, 0.5) * WEIGHTS["road_condition"]
    bridge_component = CONDITION_SCORE.get(bridge_condition, 0.5) * WEIGHTS["bridge_condition"]
    incident_component = min(recent_incidents / 5.0, 1.0) * WEIGHTS["recent_incidents"]
    terrain_component = min(max(terrain_difficulty, 0.0), 1.0) * WEIGHTS["terrain_difficulty"]

    score = rainfall_component + road_component + bridge_component + incident_component + terrain_component
    score = round(min(score, 100.0), 1)

    if score < 35:
        level = "LOW"
    elif score < 65:
        level = "MEDIUM"
    else:
        level = "HIGH"

    contributions = {
        "heavy rainfall": rainfall_component,
        "poor road condition": road_component,
        "poor bridge condition": bridge_component,
        "recent incidents on this route": incident_component,
        "difficult terrain": terrain_component,
    }
    factors = [k for k, v in sorted(contributions.items(), key=lambda x: -x[1]) if v > 5][:3]
    if not factors:
        factors = ["no significant risk factors detected"]

    return {
        "risk_score": score, 
        "risk_level": level, 
        "factors": factors,
        "prediction_source": "tier1_fallback"
    }

def compute_bulk_risk_scores(features_list: list) -> list:
    """Batch evaluation of risk scores for multiple roads."""
    # Attempt ML inference first
    ml_results = ml_service.predict_bulk(features_list)
    
    final_results = []
    
    for row, (ml_score, source) in zip(features_list, ml_results):
        if source == "ml" and ml_score is not None:
            score = ml_score
            if score < 35:
                level = "LOW"
            elif score < 65:
                level = "MEDIUM"
            else:
                level = "HIGH"
            final_results.append({
                "risk_score": score, 
                "risk_level": level, 
                "factors": ["AI-driven disruption prediction"],
                "prediction_source": "ml"
            })
            continue

        # Tier 1 Fallback
        rainfall_mm = row.get("rainfall_mm", 0.0)
        road_condition = row.get("road_condition", "fair")
        bridge_condition = row.get("bridge_condition", "fair")
        recent_incidents = row.get("recent_incidents", 0)
        terrain_difficulty = row.get("terrain_difficulty", 0.3)

        rainfall_component = min(rainfall_mm / 100.0, 1.0) * WEIGHTS["rainfall"]
        road_component = CONDITION_SCORE.get(road_condition, 0.5) * WEIGHTS["road_condition"]
        bridge_component = CONDITION_SCORE.get(bridge_condition, 0.5) * WEIGHTS["bridge_condition"]
        incident_component = min(recent_incidents / 5.0, 1.0) * WEIGHTS["recent_incidents"]
        terrain_component = min(max(terrain_difficulty, 0.0), 1.0) * WEIGHTS["terrain_difficulty"]

        score = rainfall_component + road_component + bridge_component + incident_component + terrain_component
        score = round(min(score, 100.0), 1)

        if score < 35:
            level = "LOW"
        elif score < 65:
            level = "MEDIUM"
        else:
            level = "HIGH"

        contributions = {
            "heavy rainfall": rainfall_component,
            "poor road condition": road_component,
            "poor bridge condition": bridge_component,
            "recent incidents on this route": incident_component,
            "difficult terrain": terrain_component,
        }
        factors = [k for k, v in sorted(contributions.items(), key=lambda x: -x[1]) if v > 5][:3]
        if not factors:
            factors = ["no significant risk factors detected"]

        final_results.append({
            "risk_score": score, 
            "risk_level": level, 
            "factors": factors,
            "prediction_source": "tier1_fallback"
        })
        
    return final_results

