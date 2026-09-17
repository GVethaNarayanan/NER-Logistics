"""
Tier 2 ML training script.

Real data goes in: data/historical_disruptions.csv
(see data/historical_disruptions.csv.example for the exact column format --
 fill this in as you compile real events from NDMA/ASDMA/BRO bulletins and
 news reports, per DATASET_RESEARCH.md).

Until that file has enough real rows, this script trains on synthetic rows
generated from the SAME rule engine used in app/services/risk_engine.py, so
Tier 1 and Tier 2 stay consistent with each other rather than contradicting.
"""
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.services.risk_engine import compute_risk_score  # noqa: E402


def generate_synthetic_rows(n=300, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        rainfall = rng.uniform(0, 150)
        road_cond = rng.choice(["good", "fair", "poor"])
        bridge_cond = rng.choice(["good", "fair", "poor"])
        incidents = int(rng.integers(0, 6))
        terrain = rng.uniform(0, 1)
        result = compute_risk_score(rainfall, road_cond, bridge_cond, incidents, terrain)
        disrupted = 1 if result["risk_level"] == "HIGH" else 0
        rows.append(
            {
                "rainfall_mm": rainfall,
                "road_condition": road_cond,
                "bridge_condition": bridge_cond,
                "recent_incidents": incidents,
                "terrain_difficulty": terrain,
                "disrupted": disrupted,
            }
        )
    return pd.DataFrame(rows)


def load_dataset() -> pd.DataFrame:
    real_path = "data/historical_disruptions.csv"
    if os.path.exists(real_path):
        real_df = pd.read_csv(real_path)
        if "source" in real_df.columns:
            real_df = real_df.drop(columns=["source"])
        print(f"Loaded {len(real_df)} real compiled events from {real_path}")
    else:
        real_df = pd.DataFrame()
        print(
            "No compiled real dataset found yet -- training on synthetic data only. "
            "Copy data/historical_disruptions.csv.example to "
            "data/historical_disruptions.csv and start adding real events."
        )
    synthetic_df = generate_synthetic_rows()
    return pd.concat([real_df, synthetic_df], ignore_index=True)


def main():
    df = load_dataset()

    le_road = LabelEncoder()
    le_bridge = LabelEncoder()
    df["road_condition_enc"] = le_road.fit_transform(df["road_condition"])
    df["bridge_condition_enc"] = le_bridge.fit_transform(df["bridge_condition"])

    feature_cols = [
        "rainfall_mm",
        "road_condition_enc",
        "bridge_condition_enc",
        "recent_incidents",
        "terrain_difficulty",
    ]
    X = df[feature_cols]
    y = df["disrupted"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000),
        "random_forest": RandomForestClassifier(n_estimators=200, random_state=42),
    }

    best_model, best_f1, best_name = None, -1.0, None
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        print(f"\n--- {name} ---")
        print(classification_report(y_test, preds, zero_division=0))
        print(confusion_matrix(y_test, preds))
        report = classification_report(y_test, preds, output_dict=True, zero_division=0)
        f1 = report["weighted avg"]["f1-score"]
        if f1 > best_f1:
            best_model, best_f1, best_name = model, f1, name

    os.makedirs("ml", exist_ok=True)
    joblib.dump(
        {"model": best_model, "road_encoder": le_road, "bridge_encoder": le_bridge},
        "ml/risk_model.joblib",
    )
    print(f"\nBest model: {best_name} (weighted F1={best_f1:.2f}) saved to ml/risk_model.joblib")


if __name__ == "__main__":
    main()
