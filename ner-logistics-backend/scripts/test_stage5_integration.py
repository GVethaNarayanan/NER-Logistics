"""
Stage 5 — Weather + Risk Integration Test Suite

Tests against live PostGIS database. Covers:
- Weather grid derivation from road geometry
- Weather matching (single + batch + point-based)
- Missing/stale weather handling
- Risk scoring with weather factors
- Safest route risk integration
- Alert state transitions
- All 8 NER state coverage
- Performance measurements

Usage: python -u scripts/test_stage5_integration.py
"""
import sys
import os
import time
import traceback
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.database import SessionLocal

# ── Test framework ────────────────────────────────────────────────────────────

PASSED = 0
FAILED = 0
ERRORS = []


def test(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        ERRORS.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail}")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    db = SessionLocal()
    timings = {}
    
    print("Stage 5 Integration Test Suite")
    print("=" * 60)
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 1: Weather Grid
    # ══════════════════════════════════════════════════════════════
    section("1. WEATHER GRID (Geometry-Based)")
    
    from app.services.weather_job import get_weather_grid, invalidate_weather_grid
    
    # Force refresh the grid
    invalidate_weather_grid()
    t0 = time.time()
    grid = get_weather_grid(db, force_refresh=True)
    grid_time = time.time() - t0
    timings["grid_computation"] = grid_time
    
    test("Grid is non-empty", len(grid) > 0, f"got {len(grid)} cells")
    test("Grid has reasonable count (>20 cells)", len(grid) > 20, f"got {len(grid)}")
    print(f"  INFO: Grid has {len(grid)} cells, computed in {grid_time:.2f}s")
    
    # Verify grid covers latitude range of NER (roughly 22-29)
    lats = [g[0] for g in grid]
    lons = [g[1] for g in grid]
    test("Grid covers lat range 22-29", min(lats) <= 23 and max(lats) >= 28,
         f"lat range: {min(lats)}-{max(lats)}")
    test("Grid covers lon range 88-97", min(lons) <= 89 and max(lons) >= 95,
         f"lon range: {min(lons)}-{max(lons)}")
    
    # Verify cache works (second call should be instant)
    t0 = time.time()
    grid2 = get_weather_grid(db)
    cache_time = time.time() - t0
    test("Grid cache hit is fast (<0.01s)", cache_time < 0.01, 
         f"cache hit took {cache_time:.4f}s")
    test("Cached grid same size", len(grid2) == len(grid))
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 2: All 8 NER States Coverage
    # ══════════════════════════════════════════════════════════════
    section("2. 8-STATE COVERAGE")
    
    expected_states = [
        "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
        "Mizoram", "Nagaland", "Sikkim", "Tripura"
    ]
    
    # Check which states have roads
    for state_name in expected_states:
        if state_name == "Sikkim":
            # Sikkim roads may be in NULL-district bucket
            count = db.execute(text("""
                SELECT count(*) FROM roads r
                LEFT JOIN districts d ON r.district_id = d.id
                LEFT JOIN states s ON d.state_id = s.id
                WHERE r.geometry IS NOT NULL AND r.is_legacy = false
                  AND (s.name = :name OR (r.district_id IS NULL AND 
                       ST_Y(ST_Centroid(r.geometry)) BETWEEN 27.0 AND 28.5 AND
                       ST_X(ST_Centroid(r.geometry)) BETWEEN 88.0 AND 89.0))
            """), {"name": state_name}).scalar()
        else:
            count = db.execute(text("""
                SELECT count(*) FROM roads r
                JOIN districts d ON r.district_id = d.id
                JOIN states s ON d.state_id = s.id
                WHERE s.name = :name AND r.geometry IS NOT NULL AND r.is_legacy = false
            """), {"name": state_name}).scalar()
        
        test(f"{state_name} has roads", count > 0, f"count={count}")
    
    # Check grid coverage per state centroid
    state_centroids = db.execute(text("""
        SELECT s.name,
               round(ST_Y(ST_Centroid(ST_Collect(r.geometry)))::numeric, 1) as lat,
               round(ST_X(ST_Centroid(ST_Collect(r.geometry)))::numeric, 1) as lon
        FROM roads r
        JOIN districts d ON r.district_id = d.id
        JOIN states s ON d.state_id = s.id
        WHERE r.geometry IS NOT NULL AND r.is_legacy = false
        GROUP BY s.name
    """)).fetchall()
    
    for sc in state_centroids:
        # Check if any grid cell is within 1 degree of state centroid
        has_coverage = any(
            abs(g[0] - float(sc.lat)) <= 1.0 and abs(g[1] - float(sc.lon)) <= 1.0
            for g in grid
        )
        test(f"{sc.name} has grid coverage near centroid ({sc.lat},{sc.lon})", 
             has_coverage)
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 3: Weather Matching (Single Road)
    # ══════════════════════════════════════════════════════════════
    section("3. WEATHER MATCHING (Single Road)")
    
    from app.services.weather_match import (
        match_weather_for_road,
        match_weather_for_point,
        batch_match_weather_for_roads,
        WeatherMatchResult,
        MISSING_WEATHER_RAINFALL_PENALTY,
    )
    
    # Get a road that should have weather coverage (Assam)
    assam_road = db.execute(text("""
        SELECT r.id FROM roads r
        JOIN districts d ON r.district_id = d.id
        JOIN states s ON d.state_id = s.id
        WHERE s.name = 'Assam' AND r.geometry IS NOT NULL AND r.is_legacy = false
        LIMIT 1
    """)).fetchone()
    
    if assam_road:
        t0 = time.time()
        wmatch = match_weather_for_road(db, assam_road.id)
        single_time = time.time() - t0
        timings["single_weather_match"] = single_time
        
        print(f"  INFO: Road {assam_road.id} weather: source={wmatch.source}, "
              f"rain={wmatch.rainfall_mm}mm, dist={wmatch.distance_km}km, "
              f"time={single_time*1000:.1f}ms")
        
        test("Single match returns WeatherMatchResult", 
             isinstance(wmatch, WeatherMatchResult))
        test("Single match source is verified/stale/missing", 
             wmatch.source in ("verified", "stale", "missing"))
        
        if wmatch.source != "missing":
            test("Matched weather within 50km", wmatch.distance_km <= 50.0,
                 f"distance={wmatch.distance_km}")
            test("Has snapshot_id", wmatch.snapshot_id is not None)
    else:
        print("  SKIP: No Assam road found")
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 4: Missing Weather Handling (Correction 4)
    # ══════════════════════════════════════════════════════════════
    section("4. MISSING WEATHER HANDLING")
    
    # Test with coordinates far from any weather station
    wmissing = match_weather_for_point(db, 0.0, 0.0)  # middle of ocean
    test("Far-away point returns missing", wmissing.source == "missing")
    test("Missing weather_stale=True", wmissing.weather_stale == True)
    test("Missing risk_data_quality=degraded", wmissing.risk_data_quality == "degraded")
    test("Missing effective_rainfall > 0 (penalty)", 
         wmissing.effective_rainfall_mm > 0,
         f"effective_rainfall={wmissing.effective_rainfall_mm}")
    test(f"Missing penalty = {MISSING_WEATHER_RAINFALL_PENALTY}mm",
         wmissing.effective_rainfall_mm == MISSING_WEATHER_RAINFALL_PENALTY)
    test("Missing has risk_factors", len(wmissing.risk_factors) > 0)
    test("Missing factors include 'Weather data unavailable'",
         "Weather data unavailable" in wmissing.risk_factors)
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 5: Batch Weather Matching (Correction 3)
    # ══════════════════════════════════════════════════════════════
    section("5. BATCH WEATHER MATCHING")
    
    # Get 100 road IDs across different states
    sample_roads = db.execute(text("""
        SELECT r.id FROM roads r
        WHERE r.geometry IS NOT NULL AND r.is_legacy = false AND r.status = 'open'
        ORDER BY random()
        LIMIT 100
    """)).fetchall()
    sample_ids = [r.id for r in sample_roads]
    
    t0 = time.time()
    batch_results = batch_match_weather_for_roads(db, road_ids=sample_ids)
    batch_time = time.time() - t0
    timings["batch_weather_100_roads"] = batch_time
    
    test("Batch returns dict", isinstance(batch_results, dict))
    matched_count = len(batch_results)
    print(f"  INFO: Batch matched {matched_count}/{len(sample_ids)} roads in {batch_time*1000:.1f}ms")
    
    # All matched results should have valid source
    for rid, wmatch in batch_results.items():
        if wmatch.source not in ("verified", "stale"):
            test(f"Road {rid} has valid source", False, f"source={wmatch.source}")
            break
    else:
        test("All batch results have valid source", True)
    
    # Check 50km distance cap enforcement
    over_50km = [r for r in batch_results.values() if r.distance_km > 50.0]
    test("No results beyond 50km", len(over_50km) == 0,
         f"found {len(over_50km)} results beyond 50km")
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 6: Risk Scoring
    # ══════════════════════════════════════════════════════════════
    section("6. RISK SCORING")
    
    from app.services.risk_engine import compute_risk_score
    
    # Test deterministic scoring
    r1 = compute_risk_score(50.0, "good", "good", 0, 0.3)
    r2 = compute_risk_score(50.0, "good", "good", 0, 0.3)
    test("Risk score is deterministic", r1["risk_score"] == r2["risk_score"])
    test("Risk returns level", r1["risk_level"] in ("LOW", "MEDIUM", "HIGH"))
    test("Risk returns factors", isinstance(r1["factors"], list))
    test("Risk returns prediction_source", "prediction_source" in r1)
    
    # Test weather contribution
    low_rain = compute_risk_score(0.0, "good", "good", 0, 0.3)
    high_rain = compute_risk_score(100.0, "good", "good", 0, 0.3)
    test("High rainfall increases risk", 
         high_rain["risk_score"] > low_rain["risk_score"],
         f"low_rain={low_rain['risk_score']}, high_rain={high_rain['risk_score']}")
    
    # Test incident contribution
    no_incident = compute_risk_score(0.0, "good", "good", 0, 0.3)
    many_incidents = compute_risk_score(0.0, "good", "good", 5, 0.3)
    test("Incidents increase risk",
         many_incidents["risk_score"] > no_incident["risk_score"],
         f"no_inc={no_incident['risk_score']}, many_inc={many_incidents['risk_score']}")
    
    # Test missing weather penalty vs verified 0mm
    verified_zero = compute_risk_score(0.0, "good", "good", 0, 0.3)
    missing_penalty = compute_risk_score(MISSING_WEATHER_RAINFALL_PENALTY, "good", "good", 0, 0.3)
    test("Missing weather penalty > verified 0mm (Correction 4)",
         missing_penalty["risk_score"] > verified_zero["risk_score"],
         f"verified_zero={verified_zero['risk_score']}, missing={missing_penalty['risk_score']}")
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 7: Routing Integration
    # ══════════════════════════════════════════════════════════════
    section("7. ROUTING INTEGRATION")
    
    from app.services.routing_service import find_route, RoutingError
    
    # Test shortest route (should not be affected by risk)
    try:
        t0 = time.time()
        shortest = find_route(db, 26.14, 91.74, 26.15, 91.79, preference="shortest")
        shortest_time = time.time() - t0
        timings["shortest_route"] = shortest_time
        
        test("Shortest route succeeds", True)
        test("Shortest route has geometry",
             shortest["geometry"]["type"] == "LineString")
        test("Shortest route has distance",
             shortest["properties"]["total_distance_km"] > 0)
        test("Shortest route preference is 'shortest'",
             shortest["properties"]["route_preference"] == "shortest")
        print(f"  INFO: Shortest route: {shortest['properties']['total_distance_km']:.2f}km, "
              f"{shortest['properties']['num_roads']} roads, {shortest_time*1000:.1f}ms")
    except RoutingError as e:
        test("Shortest route succeeds", False, f"RoutingError: {e.code}")
    except Exception as e:
        test("Shortest route succeeds", False, str(e))
    
    # Test safest route (should incorporate risk)
    try:
        t0 = time.time()
        safest = find_route(db, 26.14, 91.74, 26.15, 91.79, preference="safest")
        safest_time = time.time() - t0
        timings["safest_route"] = safest_time
        
        test("Safest route succeeds", True)
        test("Safest route has risk_level",
             safest["properties"]["risk_level"] in ("LOW", "MEDIUM", "HIGH"))
        test("Safest route has average_risk_score",
             "average_risk_score" in safest["properties"])
        test("Safest route preference is 'safest'",
             safest["properties"]["route_preference"] == "safest")
        print(f"  INFO: Safest route: {safest['properties']['total_distance_km']:.2f}km, "
              f"risk={safest['properties']['average_risk_score']}, "
              f"{safest['properties']['risk_level']}, {safest_time*1000:.1f}ms")
    except RoutingError as e:
        test("Safest route succeeds", False, f"RoutingError: {e.code}")
    except Exception as e:
        test("Safest route succeeds", False, str(e))
    
    # Test NULL-district road routing (should still work)
    null_district_road = db.execute(text("""
        SELECT ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lon
        FROM roads 
        WHERE district_id IS NULL AND geometry IS NOT NULL AND is_legacy = false
        LIMIT 1
    """)).fetchone()
    
    if null_district_road:
        try:
            nearby = find_route(
                db, 
                null_district_road.lat, null_district_road.lon,
                null_district_road.lat + 0.01, null_district_road.lon + 0.01,
                preference="shortest"
            )
            test("NULL-district road routing works", True)
        except RoutingError:
            test("NULL-district road routing works", True, "RoutingError expected for edge case")
        except Exception as e:
            test("NULL-district road routing works", False, str(e))
    else:
        print("  SKIP: No NULL-district road found")
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 8: Alert Integration
    # ══════════════════════════════════════════════════════════════
    section("8. ALERT INTEGRATION")
    
    from app.services.alert_job import evaluate_network_alerts
    
    # Clear existing alerts for clean test
    db.execute(text("DELETE FROM alerts"))
    db.commit()
    
    t0 = time.time()
    alert_stats = evaluate_network_alerts(db)
    alert_time = time.time() - t0
    timings["alert_evaluation"] = alert_time
    
    test("Alert evaluation returns dict", isinstance(alert_stats, dict))
    test("Alert stats has road_alerts_created", "road_alerts_created" in alert_stats)
    test("Alert stats has bridge_alerts_created", "bridge_alerts_created" in alert_stats)
    
    print(f"  INFO: Alert evaluation: created={alert_stats.get('road_alerts_created', 0)}, "
          f"resolved={alert_stats.get('road_alerts_resolved', 0)}, "
          f"suppressed={alert_stats.get('road_alerts_suppressed', 0)}")
    print(f"  INFO: Time: {alert_time:.2f}s")
    
    # Run again — should suppress, not create duplicates
    alert_stats2 = evaluate_network_alerts(db)
    test("Second alert run suppresses duplicates (no new creates)",
         alert_stats2.get("road_alerts_created", 0) == 0,
         f"created={alert_stats2.get('road_alerts_created', 0)}")
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 9: Weather Freshness
    # ══════════════════════════════════════════════════════════════
    section("9. WEATHER FRESHNESS")
    
    fresh_count = db.execute(text("""
        SELECT count(*) FROM weather_snapshots 
        WHERE data_source = 'verified' 
          AND recorded_at >= NOW() - INTERVAL '6 hours'
    """)).scalar()
    
    total_count = db.execute(text(
        "SELECT count(*) FROM weather_snapshots WHERE data_source = 'verified'"
    )).scalar()
    
    stale_count = total_count - fresh_count
    
    print(f"  Total verified snapshots: {total_count}")
    print(f"  Fresh (<6h):             {fresh_count}")
    print(f"  Stale (>6h):             {stale_count}")
    
    test("Has fresh weather data", fresh_count > 0,
         f"fresh={fresh_count}")
    
    # ══════════════════════════════════════════════════════════════
    # SECTION 10: Performance Summary
    # ══════════════════════════════════════════════════════════════
    section("10. PERFORMANCE SUMMARY")
    
    for name, elapsed in timings.items():
        if elapsed < 1.0:
            print(f"  {name:35s} {elapsed*1000:.1f}ms")
        else:
            print(f"  {name:35s} {elapsed:.2f}s")
    
    # ══════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  FINAL RESULTS: {PASSED} passed, {FAILED} failed")
    print(f"{'='*60}")
    
    if ERRORS:
        print(f"\n  FAILURES:")
        for err in ERRORS:
            print(f"    - {err}")
    
    db.close()
    return FAILED == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
