from fastapi import APIRouter
from app.services import weather_client

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/current")
def current_weather(lat: float, lon: float):
    return weather_client.get_current_and_forecast(lat, lon)


@router.get("/historical")
def historical_weather(lat: float, lon: float, start_date: str, end_date: str):
    return weather_client.get_historical(lat, lon, start_date, end_date)
