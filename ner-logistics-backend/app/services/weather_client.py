"""
Thin client for the Open-Meteo API -- free, no API key required.

Forecast/current : https://api.open-meteo.com/v1/forecast
Historical archive (hourly data back to 1940): https://archive-api.open-meteo.com/v1/archive
"""
import requests
from app.config import settings


def get_current_and_forecast(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "forecast_days": 7,
        "timezone": "auto",
    }
    resp = requests.get(settings.open_meteo_forecast_url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_historical(lat: float, lon: float, start_date: str, end_date: str) -> dict:
    """start_date/end_date format: YYYY-MM-DD"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,precipitation",
        "timezone": "auto",
    }
    resp = requests.get(settings.open_meteo_archive_url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()
