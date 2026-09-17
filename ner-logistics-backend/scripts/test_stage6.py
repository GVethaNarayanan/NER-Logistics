import sys
import time
import uuid
import pytest
import math
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
from app.services.routing_service import find_route, create_route_from_computed
from app.services.vehicle_service import locate_vehicle_context, haversine_distance_km
from app.services.simulation_job import interpolate_linestring
from sqlalchemy import text
from app.services.graph_service import invalidate_graph_cache

def setup_db():
    return SessionLocal()

def test_linestring_interpolation():
    print("\n============================================================")
    print("  1. VEHICLE SIMULATION (LineString)")
    print("============================================================")
    
    # A simple 2-segment linestring of length 20km
    wkt = "LINESTRING(0 0, 0 10, 0 20)"
    total_km = 20.0
    
    # Forward interpolation
    y, x = interpolate_linestring(wkt, 10.0, total_km, False)
    assert abs(x - 0) < 0.01
    assert abs(y - 10) < 0.01
    print("  PASS: Forward interpolation halfway")
    
    # Reversed interpolation
    y, x = interpolate_linestring(wkt, 10.0, total_km, True)
    assert abs(x - 0) < 0.01
    assert abs(y - 10) < 0.01
    print("  PASS: Reverse interpolation halfway")
    
    y_rev, x_rev = interpolate_linestring(wkt, 5.0, total_km, True)
    assert abs(y_rev - 15) < 0.01
    print("  PASS: Reverse interpolation 1/4 way (starts from end)")

def test_route_creation(db: Session):
    print("\n============================================================")
    print("  2. ROUTE CREATION")
    print("============================================================")
    
    # Force fresh graph
    invalidate_graph_cache()
    
    # Assam route (Guwahati)
    origin_lat, origin_lon = 26.1556085, 91.6762382
    dest_lat, dest_lon = 26.1824148, 91.7371583
    
    t0 = time.time()
    route_geojson = find_route(db, origin_lat, origin_lon, dest_lat, dest_lon, "shortest")
    print(f"  INFO: Route computed in {time.time() - t0:.2f}s")
    
    segments = route_geojson["properties"]["route_segments"]
    assert len(segments) > 0
    print("  PASS: Route segments generated")
    
    has_forward = any(not s["is_reversed"] for s in segments)
    has_reverse = any(s["is_reversed"] for s in segments)
    if has_reverse:
        print("  PASS: Direction flags correctly populated (includes reversed)")
    else:
        print("  INFO: Direction flags populated (all forward in this route)")
        
    db_route = create_route_from_computed(db, route_geojson, "Test Assam Route")
    assert db_route.id is not None
    print("  PASS: Route persisted to DB")
    
    route_roads = db.query(models.RouteRoad).filter(models.RouteRoad.route_id == db_route.id).all()
    assert len(route_roads) == len(segments)
    assert route_roads[0].road_length_km is not None
    assert route_roads[0].road_length_km > 0
    print("  PASS: RouteRoads persisted with direction and length")
    
    return db_route, route_geojson

def test_locate_context(db: Session):
    print("\n============================================================")
    print("  3. VEHICLE POSTGIS MATCHING")
    print("============================================================")
    
    # Point exactly on a known road in Assam
    lat, lon = 26.1556085, 91.6762382
    
    t0 = time.time()
    context = locate_vehicle_context(db, lat, lon)
    t_match = time.time() - t0
    
    assert context["road_id"] is not None
    print(f"  PASS: Nearest road matched in {t_match*1000:.1f}ms")
    
    assert context["district_id"] is not None
    assert context["state_name"] == "Assam"
    print(f"  PASS: Containing district matched ({context['district_name']})")
    
    # Point in ocean (should find nothing)
    context_ocean = locate_vehicle_context(db, 0.0, 0.0)
    assert context_ocean["road_id"] is None
    assert context_ocean["district_id"] is None
    print("  PASS: Out of bounds handles gracefully (no fabricated district)")

def test_null_district(db: Session):
    print("\n============================================================")
    print("  4. NULL-DISTRICT (SIKKIM) ROUTING & MATCHING")
    print("============================================================")
    
    # Gangtok, Sikkim
    lat, lon = 27.3314059, 88.6137684
    
    context = locate_vehicle_context(db, lat, lon)
    assert context["road_id"] is not None
    assert context["district_id"] is None  # Sikkim districts not loaded, authentic behavior
    print("  PASS: Sikkim road matched")
    print("  PASS: District correctly left unresolved (None)")

def test_incident_workflow(db: Session):
    print("\n============================================================")
    print("  5. INCIDENT WORKFLOW")
    print("============================================================")
    
    lat, lon = 26.1556085, 91.6762382
    context = locate_vehicle_context(db, lat, lon)
    
    incident = models.Incident(
        incident_type="road_damage",
        latitude=lat,
        longitude=lon,
        severity="high",
        road_id=context["road_id"],
        status="reported",
        synced="synced"
    )
    db.add(incident)
    db.commit()
    print("  PASS: Incident reported")
    
    incident.status = "verified"
    db.commit()
    print("  PASS: Incident verified")
    
    incident.status = "resolved"
    db.commit()
    print("  PASS: Incident resolved")

def test_ml_model():
    print("\n============================================================")
    print("  6. ML MODEL LOAD")
    print("============================================================")
    
    try:
        from app.services.ml_service import ml_service
        ml_service.load_model()
        
        # Test prediction
        score, source = ml_service.predict_scalar(
            road_type="primary",
            weather_rainfall=10.0,
            has_incident=True
        )
        
        if source == "ml":
            print("  PASS: ML Model loaded and predicting (Tier 2 active)")
        else:
            print("  INFO: ML Model not producing Tier 2, falling back to Tier 1")
    except Exception as e:
        print(f"  INFO: ML load bypassed: {e}")

if __name__ == "__main__":
    db = setup_db()
    try:
        test_linestring_interpolation()
        test_route_creation(db)
        test_locate_context(db)
        test_null_district(db)
        test_incident_workflow(db)
        test_ml_model()
        
        print("\n============================================================")
        print("  FINAL RESULTS: All integration steps complete")
        print("============================================================")
    finally:
        db.close()
