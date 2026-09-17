"""
Pull current + 7-day forecast weather for NER state capitals using
Open-Meteo (free, no API key needed).

Usage: python scripts/fetch_weather.py
"""
import sys
import os
import json

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.services import weather_client  # noqa: E402

NER_CAPITALS = {
    "Guwahati": (26.1445, 91.7362),
    "Shillong": (25.5788, 91.8933),
    "Imphal": (24.8170, 93.9368),
    "Aizawl": (23.7271, 92.7176),
    "Kohima": (25.6751, 94.1086),
    "Agartala": (23.8315, 91.2868),
    "Itanagar": (27.0844, 93.6053),
    "Gangtok": (27.3389, 88.6065),
}

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    for city, (lat, lon) in NER_CAPITALS.items():
        data = weather_client.get_current_and_forecast(lat, lon)
        out_path = f"data/weather_{city.lower()}.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved current+forecast weather for {city} -> {out_path}")
