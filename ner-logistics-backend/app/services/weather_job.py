"""
Stage 5 — Weather Fetch Job (Geometry-Based)

Periodic job to fetch weather for configured NER road locations.

Key design decisions (Correction 1):
- Weather sampling grid is derived from ST_Centroid(road.geometry),
  NOT from the old start_lat/start_lon fields.
- Grid is CACHED and only recomputed when:
  (a) the grid cache is missing
  (b) the road network changes (via explicit invalidation)
  (c) an explicit refresh is requested
- Grid cells are rounded to 1 decimal place (~11km) matching Open-Meteo's
  native ~10km resolution. This deduplicates 226k roads into ~42 grid cells.
- Does NOT fetch one weather API call per road.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import WeatherSnapshot
from app.services.weather_client import get_current_and_forecast

logger = logging.getLogger("ner_logistics.weather_job")

# ── Grid Cache (Correction 1) ────────────────────────────────────────────────
# The weather sampling grid is computed once from road geometry centroids
# and cached in memory. It is only recomputed when explicitly invalidated.

_GRID_CACHE: Optional[List[Tuple[float, float]]] = None
_GRID_CACHE_LOCK = threading.Lock()
_GRID_CACHE_TIME: Optional[datetime] = None


def _compute_weather_grid(db: Session) -> List[Tuple[float, float]]:
    """Derive the weather sampling grid from road geometry centroids.
    
    Returns a list of (lat, lon) tuples at 0.5-degree resolution (~55km).
    Uses PostGIS ST_Centroid, NOT the legacy start_lat/start_lon fields.
    
    Resolution rationale: 0.5° (~55km) grid ensures every road is within
    the 50km weather matching cap while keeping API calls to ~80-120 cells
    (vs ~2000 at 0.1° resolution). Open-Meteo's native resolution is ~10km
    so coarser grid cells still return accurate local weather.
    """
    t0 = time.time()
    rows = db.execute(text("""
        SELECT DISTINCT 
            round(ST_Y(ST_Centroid(geometry))::numeric * 2, 0) / 2 AS lat,
            round(ST_X(ST_Centroid(geometry))::numeric * 2, 0) / 2 AS lon
        FROM roads 
        WHERE geometry IS NOT NULL AND is_legacy = false
        ORDER BY lat, lon
    """)).fetchall()
    
    grid = [(float(r.lat), float(r.lon)) for r in rows]
    elapsed = time.time() - t0
    logger.info(
        "Weather grid computed: %d cells (0.5deg resolution) from road centroids in %.2fs", 
        len(grid), elapsed
    )
    return grid


def get_weather_grid(db: Session, force_refresh: bool = False) -> List[Tuple[float, float]]:
    """Get the cached weather sampling grid, computing it if needed.
    
    Correction 1: Grid is cached and only recomputed when:
    - Cache is empty (first call)
    - force_refresh=True (road network changed or explicit request)
    """
    global _GRID_CACHE, _GRID_CACHE_TIME
    
    with _GRID_CACHE_LOCK:
        if _GRID_CACHE is None or force_refresh:
            _GRID_CACHE = _compute_weather_grid(db)
            _GRID_CACHE_TIME = datetime.now(timezone.utc)
        return list(_GRID_CACHE)  # return a copy


def invalidate_weather_grid():
    """Invalidate the cached weather grid (call when road network changes)."""
    global _GRID_CACHE, _GRID_CACHE_TIME
    with _GRID_CACHE_LOCK:
        _GRID_CACHE = None
        _GRID_CACHE_TIME = None
    logger.info("Weather grid cache invalidated.")


def fetch_and_store_weather(force_grid_refresh: bool = False):
    """Periodic job to fetch weather for all NER road grid locations.
    
    Uses the cached weather grid (geometry-based) to determine which
    lat/lon cells to query. Does NOT call the API once per road.
    """
    logger.info("Starting periodic weather fetch job.")
    db: Session = SessionLocal()
    try:
        grid = get_weather_grid(db, force_refresh=force_grid_refresh)
        
        if not grid:
            logger.info("No grid cells found. Skipping weather fetch.")
            return

        logger.info("Fetching weather for %d grid cells...", len(grid))
        success_count = 0
        error_count = 0
        
        for lat, lon in grid:
            try:
                data = get_current_and_forecast(lat, lon)
                current = data.get("current", {})
                
                snapshot = WeatherSnapshot(
                    latitude=lat,
                    longitude=lon,
                    rainfall_mm=current.get("precipitation", 0.0),
                    temperature_c=current.get("temperature_2m"),
                    humidity_pct=current.get("relative_humidity_2m"),
                    wind_speed_kmh=current.get("wind_speed_10m"),
                    data_source="verified"
                )
                db.add(snapshot)
                db.commit()
                success_count += 1
            except Exception as e:
                logger.error(
                    "Failed to fetch weather for lat=%s, lon=%s. Error: %s", 
                    lat, lon, str(e)
                )
                db.rollback()
                error_count += 1

        logger.info(
            "Weather fetch job completed. %d/%d cells succeeded, %d errors.",
            success_count, len(grid), error_count
        )

    except Exception as e:
        logger.error("Unexpected error in weather fetch job: %s", str(e))
    finally:
        db.close()


# ── Scheduler ─────────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()

from app.services.simulation_job import run_vehicle_simulation
from app.services.alert_job import evaluate_network_alerts
from app.config import settings

def start_scheduler():
    if not scheduler.running:
        # Run every 60 minutes
        scheduler.add_job(
            fetch_and_store_weather,
            trigger=IntervalTrigger(minutes=60),
            id="weather_fetch_job",
            replace_existing=True,
        )
        # Vehicle simulator every 10 seconds (if enabled)
        if settings.vehicle_simulation_enabled:
            scheduler.add_job(
                run_vehicle_simulation,
                trigger=IntervalTrigger(seconds=10),
                id="vehicle_simulation_job",
                replace_existing=True,
            )
            logger.info("Vehicle simulation job scheduled (10s interval).")
        else:
            logger.info("Vehicle simulation job is DISABLED by configuration.")
        # Phase 11: Alert evaluation every 5 minutes (max_instances=1 for duplicate safety)
        scheduler.add_job(
            evaluate_network_alerts,
            trigger=IntervalTrigger(minutes=5),
            id="alert_evaluation_job",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Alert evaluation job scheduled (5min interval, max_instances=1).")
        scheduler.start()
        logger.info("Background scheduler started.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler shut down.")
