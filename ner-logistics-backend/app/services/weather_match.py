"""
Stage 5 — Geometry-Based Weather Matching

Provides spatial weather-to-road matching using PostGIS, with batch support
for efficient alert evaluation and route risk scoring.

Key design decisions:
- Uses ST_Centroid(road.geometry) as the representative point for each road
- Uses GiST-indexed nearest-neighbor lookup on weather_snapshots
- Enforces a 50km maximum distance cap (ST_DWithin on geography)
- Missing weather is NOT treated as safe — flagged as degraded confidence
- Batch operations avoid per-road DB query waterfalls

Weather freshness rule: snapshots must be < 6 hours old to be "verified".
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("ner_logistics.weather_match")

# ── Constants ─────────────────────────────────────────────────────────────────

WEATHER_FRESHNESS_HOURS = 6
MAX_WEATHER_DISTANCE_M = 50_000  # 50km cap per Correction 2
# Approximate degrees for ST_DWithin pre-filter (50km ≈ 0.45°)
MAX_WEATHER_DISTANCE_DEG = 0.45

# Uncertainty penalty applied when weather data is missing or stale.
# This ensures missing-weather roads do NOT appear safer than roads with
# verified weather showing 0mm rainfall. (Correction 4)
MISSING_WEATHER_RAINFALL_PENALTY = 15.0  # mm — equivalent to moderate rain


@dataclass
class WeatherMatchResult:
    """Result of matching a road/point to the nearest weather observation."""
    rainfall_mm: float = 0.0
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    source: str = "missing"        # "verified" | "stale" | "missing"
    distance_km: float = -1.0      # distance from road centroid to weather station
    snapshot_id: Optional[int] = None
    recorded_at: Optional[datetime] = None
    weather_stale: bool = True
    risk_data_quality: str = "degraded"  # "verified" | "stale" | "degraded"

    @property
    def is_missing(self) -> bool:
        return self.source == "missing"

    @property
    def effective_rainfall_mm(self) -> float:
        """Rainfall value to use for risk scoring.
        
        If weather is missing, applies uncertainty penalty so that
        missing-weather roads do NOT appear safer than verified-0mm roads.
        (Correction 4: missing weather ≠ safe)
        """
        if self.source == "missing":
            return MISSING_WEATHER_RAINFALL_PENALTY
        return self.rainfall_mm

    @property
    def risk_factors(self) -> List[str]:
        """Additional risk factors to include in scoring."""
        factors = []
        if self.source == "missing":
            factors.append("Weather data unavailable")
        elif self.source == "stale":
            factors.append("Weather data stale (>6h old)")
        return factors


def _make_missing_result() -> WeatherMatchResult:
    """Create a result for roads with no weather coverage."""
    return WeatherMatchResult(
        rainfall_mm=0.0,
        source="missing",
        weather_stale=True,
        risk_data_quality="degraded",
    )


# ── Single-Road Matching ─────────────────────────────────────────────────────

def match_weather_for_road(db: Session, road_id: int) -> WeatherMatchResult:
    """Match a single road to the nearest fresh weather snapshot using geometry.
    
    Uses ST_Centroid(road.geometry) and nearest-neighbor lookup on the
    GiST-indexed weather_snapshots table.
    
    Returns WeatherMatchResult with source="missing" if no weather within 50km.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    six_hours_ago = now_utc - timedelta(hours=WEATHER_FRESHNESS_HOURS)

    result = db.execute(text("""
        SELECT w.id, w.rainfall_mm, w.temperature_c, w.humidity_pct,
               w.wind_speed_kmh, w.recorded_at, w.data_source,
               ST_Distance(
                   ST_Centroid(r.geometry)::geography,
                   ST_SetSRID(ST_MakePoint(w.longitude, w.latitude), 4326)::geography
               ) as dist_m
        FROM roads r
        CROSS JOIN LATERAL (
            SELECT * FROM weather_snapshots ws
            WHERE ws.data_source = 'verified'
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(ws.longitude, ws.latitude), 4326),
                  ST_Centroid(r.geometry),
                  :max_dist_deg
              )
            ORDER BY ST_SetSRID(ST_MakePoint(ws.longitude, ws.latitude), 4326)
                     <-> ST_Centroid(r.geometry)
            LIMIT 1
        ) w
        WHERE r.id = :road_id AND r.geometry IS NOT NULL
    """), {
        "road_id": road_id,
        "max_dist_deg": MAX_WEATHER_DISTANCE_DEG,
    }).fetchone()

    if result is None:
        return _make_missing_result()

    dist_km = result.dist_m / 1000.0
    is_stale = result.recorded_at < six_hours_ago if result.recorded_at else True

    if is_stale:
        source = "stale"
        quality = "stale"
    else:
        source = "verified"
        quality = "verified"

    return WeatherMatchResult(
        rainfall_mm=result.rainfall_mm or 0.0,
        temperature_c=result.temperature_c,
        humidity_pct=result.humidity_pct,
        wind_speed_kmh=result.wind_speed_kmh,
        source=source,
        distance_km=round(dist_km, 2),
        snapshot_id=result.id,
        recorded_at=result.recorded_at,
        weather_stale=is_stale,
        risk_data_quality=quality,
    )


def match_weather_for_point(db: Session, lat: float, lon: float) -> WeatherMatchResult:
    """Match arbitrary coordinates to the nearest fresh weather snapshot.
    
    Used by the risk router when a road_id provides geometry, and as a
    fallback for roads without geometry.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    six_hours_ago = now_utc - timedelta(hours=WEATHER_FRESHNESS_HOURS)

    result = db.execute(text("""
        SELECT w.id, w.rainfall_mm, w.temperature_c, w.humidity_pct,
               w.wind_speed_kmh, w.recorded_at, w.data_source,
               ST_Distance(
                   ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(w.longitude, w.latitude), 4326)::geography
               ) as dist_m
        FROM weather_snapshots w
        WHERE w.data_source = 'verified'
          AND ST_DWithin(
              ST_SetSRID(ST_MakePoint(w.longitude, w.latitude), 4326),
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
              :max_dist_deg
          )
        ORDER BY ST_SetSRID(ST_MakePoint(w.longitude, w.latitude), 4326)
                 <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
        LIMIT 1
    """), {
        "lat": lat,
        "lon": lon,
        "max_dist_deg": MAX_WEATHER_DISTANCE_DEG,
    }).fetchone()

    if result is None:
        return _make_missing_result()

    dist_km = result.dist_m / 1000.0
    is_stale = result.recorded_at < six_hours_ago if result.recorded_at else True

    if is_stale:
        source = "stale"
        quality = "stale"
    else:
        source = "verified"
        quality = "verified"

    return WeatherMatchResult(
        rainfall_mm=result.rainfall_mm or 0.0,
        temperature_c=result.temperature_c,
        humidity_pct=result.humidity_pct,
        wind_speed_kmh=result.wind_speed_kmh,
        source=source,
        distance_km=round(dist_km, 2),
        snapshot_id=result.id,
        recorded_at=result.recorded_at,
        weather_stale=is_stale,
        risk_data_quality=quality,
    )


# ── Batch Road Matching (for alerts + routing) ───────────────────────────────

def batch_match_weather_for_roads(
    db: Session,
    road_ids: Optional[List[int]] = None,
) -> Dict[int, WeatherMatchResult]:
    """Batch-match roads to nearest weather snapshots using PostGIS.
    
    If road_ids is None, matches ALL open non-legacy roads (for alert evaluation).
    If road_ids is a list, matches only those roads (for route risk scoring).
    
    Uses CROSS JOIN LATERAL with ST_DWithin distance cap of 50km.
    Returns dict mapping road_id -> WeatherMatchResult.
    
    Correction 2: Enforces 50km maximum via ST_DWithin(..., 50000) on geography.
    Correction 3: Single batch query instead of per-road waterfalls.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    six_hours_ago = now_utc - timedelta(hours=WEATHER_FRESHNESS_HOURS)

    if road_ids is not None and len(road_ids) == 0:
        return {}

    # Fast check: If no weather snapshots exist in the DB, return empty dict immediately
    has_snapshots = db.execute(text("SELECT 1 FROM weather_snapshots LIMIT 1")).fetchone()
    if not has_snapshots:
        return {}

    # Build the road filter clause
    if road_ids is not None:
        road_filter = "AND r.id = ANY(:road_ids)"
        params = {
            "max_dist_deg": MAX_WEATHER_DISTANCE_DEG,
            "six_hours_ago": six_hours_ago,
            "road_ids": road_ids,
        }
    else:
        road_filter = "AND r.status = 'open' AND r.is_legacy = false"
        params = {
            "max_dist_deg": MAX_WEATHER_DISTANCE_DEG,
            "six_hours_ago": six_hours_ago,
        }

    query = text(f"""
        SELECT r.id as road_id,
               w.id as snapshot_id,
               w.rainfall_mm,
               w.temperature_c,
               w.humidity_pct,
               w.wind_speed_kmh,
               w.recorded_at,
               w.data_source,
               ST_Distance(
                   ST_Centroid(r.geometry)::geography,
                   ST_SetSRID(ST_MakePoint(w.longitude, w.latitude), 4326)::geography
               ) as dist_m
        FROM roads r
        CROSS JOIN LATERAL (
            SELECT * FROM weather_snapshots ws
            WHERE ws.data_source = 'verified'
              AND ws.recorded_at >= :six_hours_ago
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(ws.longitude, ws.latitude), 4326),
                  ST_Centroid(r.geometry),
                  :max_dist_deg
              )
            ORDER BY ST_SetSRID(ST_MakePoint(ws.longitude, ws.latitude), 4326)
                     <-> ST_Centroid(r.geometry)
            LIMIT 1
        ) w
        WHERE r.geometry IS NOT NULL
          {road_filter}
    """)

    rows = db.execute(query, params).fetchall()

    results: Dict[int, WeatherMatchResult] = {}
    for row in rows:
        dist_km = row.dist_m / 1000.0 if row.dist_m else 0.0

        # Enforce hard 50km cap (ST_DWithin in degrees is approximate;
        # the geography distance is authoritative)
        if dist_km > (MAX_WEATHER_DISTANCE_M / 1000.0):
            continue

        is_stale = row.recorded_at < six_hours_ago if row.recorded_at else True

        results[row.road_id] = WeatherMatchResult(
            rainfall_mm=row.rainfall_mm or 0.0,
            temperature_c=row.temperature_c,
            humidity_pct=row.humidity_pct,
            wind_speed_kmh=row.wind_speed_kmh,
            source="stale" if is_stale else "verified",
            distance_km=round(dist_km, 2),
            snapshot_id=row.snapshot_id,
            recorded_at=row.recorded_at,
            weather_stale=is_stale,
            risk_data_quality="stale" if is_stale else "verified",
        )

    return results
