import os
import joblib
import logging
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("ner_logistics.ml_service")

class MLService:
    def __init__(self):
        self.model = None
        self.road_encoder = None
        self.bridge_encoder = None
        self.is_loaded = False
        self.disruption_idx = None
        
    def load_model(self, path: str = "ml/risk_model.joblib"):
        if not os.path.exists(path):
            logger.warning(f"No ML model found at {path}, falling back to Tier 1 heuristic.")
            return
            
        try:
            model_data = joblib.load(path)
            self.model = model_data.get("model")
            self.road_encoder = model_data.get("road_encoder")
            self.bridge_encoder = model_data.get("bridge_encoder")
            
            if not self.model or not self.road_encoder or not self.bridge_encoder:
                logger.error("ML Model artifact is missing required components. Falling back to Tier 1.")
                self.is_loaded = False
                return
                
            # Verify the model has the expected classes
            classes = list(getattr(self.model, "classes_", []))
            if 1 not in classes:
                logger.error("ML Model does not contain disruption class '1'. Disabling ML.")
                self.is_loaded = False
                return
                
            self.disruption_idx = classes.index(1)
            self.is_loaded = True
            logger.info("Successfully loaded Tier 2 ML model.")
        except Exception as e:
            logger.error(f"Failed to load ML model from {path}: {e}. Falling back to Tier 1.")
            self.is_loaded = False

    def _encode_feature(self, encoder, value: str) -> Optional[int]:
        try:
            if value in encoder.classes_:
                return int(encoder.transform([value])[0])
        except Exception:
            pass
        return None

    def predict_bulk(self, features: List[Dict[str, Any]]) -> List[Tuple[Optional[float], str]]:
        """
        Returns a list of tuples: (risk_score, prediction_source)
        risk_score is None if ML prediction is unavailable, triggering Tier 1 fallback in the caller.
        """
        if not self.is_loaded:
            return [(None, "tier1_fallback")] * len(features)
            
        valid_rows = []
        valid_indices = []
        
        for i, row in enumerate(features):
            rain = max(0.0, float(row.get("rainfall_mm", 0)))
            road = row.get("road_condition", "good")
            bridge = row.get("bridge_condition", "good")
            incidents = int(row.get("recent_incidents", 0))
            terrain = max(0.0, min(1.0, float(row.get("terrain_difficulty", 0.3))))
            
            road_enc = self._encode_feature(self.road_encoder, road)
            bridge_enc = self._encode_feature(self.bridge_encoder, bridge)
            
            if road_enc is None or bridge_enc is None:
                continue # Skip ML for this row due to unknown category
                
            valid_rows.append({
                "rainfall_mm": rain,
                "road_condition_enc": road_enc,
                "bridge_condition_enc": bridge_enc,
                "recent_incidents": incidents,
                "terrain_difficulty": terrain
            })
            valid_indices.append(i)
            
        results = [(None, "tier1_fallback")] * len(features)
        
        if not valid_rows:
            return results
            
        try:
            df = pd.DataFrame(valid_rows)
            # Ensure correct feature order explicitly
            df = df[["rainfall_mm", "road_condition_enc", "bridge_condition_enc", "recent_incidents", "terrain_difficulty"]]
            
            probas = self.model.predict_proba(df)
            disruption_probs = probas[:, self.disruption_idx]
            
            for valid_i, prob in zip(valid_indices, disruption_probs):
                score = round(float(prob) * 100.0, 1)
                results[valid_i] = (score, "ml")
                
        except Exception as e:
            logger.error(f"Batch prediction failed: {e}. Falling back to Tier 1.")
            
        return results

    def predict_scalar(self, rainfall_mm: float, road_condition: str, bridge_condition: str, recent_incidents: int, terrain_difficulty: float) -> Tuple[Optional[float], str]:
        bulk_features = [{
            "rainfall_mm": rainfall_mm,
            "road_condition": road_condition,
            "bridge_condition": bridge_condition,
            "recent_incidents": recent_incidents,
            "terrain_difficulty": terrain_difficulty
        }]
        res = self.predict_bulk(bulk_features)
        return res[0]

ml_service = MLService()
