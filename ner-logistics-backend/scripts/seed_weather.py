"""
Stage 5 — Weather Seeding Script

Fetches fresh weather data from Open-Meteo for all NER grid cells derived
from road geometry centroids. Populates the weather_snapshots table.

Usage: python scripts/seed_weather.py [--force-grid-refresh]
"""
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.database import SessionLocal
from app.models import WeatherSnapshot
from app.services.weather_client import get_current_and_forecast


def get_grid(db):
    """Derive weather grid from road geometry centroids (0.5-degree resolution)."""
    rows = db.execute(text("""
        SELECT DISTINCT 
            round(ST_Y(ST_Centroid(geometry))::numeric * 2, 0) / 2 AS lat,
            round(ST_X(ST_Centroid(geometry))::numeric * 2, 0) / 2 AS lon
        FROM roads 
        WHERE geometry IS NOT NULL AND is_legacy = false
        ORDER BY lat, lon
    """)).fetchall()
    return [(float(r.lat), float(r.lon)) for r in rows]


def verify_state_coverage(db, grid):
    """Verify which states have grid cell coverage."""
    states = db.execute(text("""
        SELECT s.name,
               round(ST_Y(ST_Centroid(ST_Collect(r.geometry)))::numeric, 1) as avg_lat,
               round(ST_X(ST_Centroid(ST_Collect(r.geometry)))::numeric, 1) as avg_lon,
               count(r.id) as road_count
        FROM roads r
        JOIN districts d ON r.district_id = d.id
        JOIN states s ON d.state_id = s.id
        WHERE r.geometry IS NOT NULL AND r.is_legacy = false
        GROUP BY s.name
        ORDER BY s.name
    """)).fetchall()
    
    # Check NULL-district roads separately  
    null_district = db.execute(text("""
        SELECT count(*) as cnt,
               round(min(ST_Y(ST_Centroid(geometry)))::numeric, 1) as min_lat,
               round(max(ST_Y(ST_Centroid(geometry)))::numeric, 1) as max_lat,
               round(min(ST_X(ST_Centroid(geometry)))::numeric, 1) as min_lon,
               round(max(ST_X(ST_Centroid(geometry)))::numeric, 1) as max_lon
        FROM roads 
        WHERE district_id IS NULL AND geometry IS NOT NULL AND is_legacy = false
    """)).fetchone()
    
    return states, null_district


def main():
    db = SessionLocal()
    
    print("=" * 70)
    print("STAGE 5 — WEATHER SEEDING")
    print("=" * 70)
    
    # Step 1: Derive grid
    print("\n[1] Deriving weather grid from road geometry centroids...")
    grid = get_grid(db)
    print(f"    Grid cells: {len(grid)}")
    
    if not grid:
        print("    ERROR: No grid cells found. Check road geometry.")
        return
    
    # Step 2: Report grid coverage
    print(f"\n[2] Grid cell listing:")
    for i, (lat, lon) in enumerate(grid):
        print(f"    {i+1:3d}. lat={lat:6.1f}  lon={lon:6.1f}")
    
    # Step 3: Verify state coverage
    print(f"\n[3] State coverage:")
    states, null_district = verify_state_coverage(db, grid)
    
    expected_states = {
        "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
        "Mizoram", "Nagaland", "Sikkim", "Tripura"
    }
    found_states = set()
    for s in states:
        found_states.add(s.name)
        print(f"    {s.name:25s} roads={s.road_count:6d}  centroid=({s.avg_lat}, {s.avg_lon})")
    
    if null_district:
        print(f"    {'(NULL-district)':25s} roads={null_district.cnt:6d}  "
              f"lat=[{null_district.min_lat}-{null_district.max_lat}]  "
              f"lon=[{null_district.min_lon}-{null_district.max_lon}]")
    
    missing_states = expected_states - found_states
    if missing_states:
        print(f"\n    WARNING: Missing states in district join: {missing_states}")
        print(f"    (These may have roads with NULL district_id — still covered by grid)")
    else:
        print(f"\n    All 8 NER states have road coverage via district join.")
    
    # Step 4: Fetch weather from Open-Meteo
    print(f"\n[4] Fetching weather from Open-Meteo for {len(grid)} grid cells...")
    success_count = 0
    error_count = 0
    t0 = time.time()
    
    for i, (lat, lon) in enumerate(grid):
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
            
            rain = current.get("precipitation", 0.0)
            temp = current.get("temperature_2m", "?")
            print(f"    [{i+1}/{len(grid)}] ({lat}, {lon}) rain={rain}mm temp={temp}C")
            
        except Exception as e:
            db.rollback()
            error_count += 1
            print(f"    [{i+1}/{len(grid)}] ({lat}, {lon}) ERROR: {e}")
        
        # Small delay to be nice to the free API
        if i < len(grid) - 1:
            time.sleep(0.1)
    
    elapsed = time.time() - t0
    
    # Step 5: Summary
    print(f"\n[5] SEEDING SUMMARY")
    print(f"    Grid cells total:    {len(grid)}")
    print(f"    Successfully fetched: {success_count}")
    print(f"    Errors:              {error_count}")
    print(f"    Elapsed time:        {elapsed:.1f}s")
    
    # Verify DB state
    total_snapshots = db.execute(text(
        "SELECT count(*) FROM weather_snapshots WHERE data_source='verified'"
    )).scalar()
    fresh_snapshots = db.execute(text("""
        SELECT count(*) FROM weather_snapshots 
        WHERE data_source='verified' 
          AND recorded_at >= NOW() - INTERVAL '6 hours'
    """)).scalar()
    
    print(f"    Total verified snapshots in DB: {total_snapshots}")
    print(f"    Fresh (< 6h) snapshots:         {fresh_snapshots}")
    
    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
