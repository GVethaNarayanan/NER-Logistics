"""
Phase 4.3 Integration Test

Tests actual routing on the live PostgreSQL/PostGIS database.
Verifies routing within different states and cross-state.
"""
import sys
import os
import time
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.services.routing_service import find_route, RoutingError

def test_route(db, label, o_lat, o_lon, d_lat, d_lon):
    print(f"\n--- Testing Route: {label} ---")
    try:
        t0 = time.time()
        res = find_route(db, o_lat, o_lon, d_lat, d_lon)
        t = time.time() - t0
        dist = res["properties"]["total_distance_km"]
        dur = res["properties"]["estimated_duration_minutes"]
        roads = res["properties"]["num_roads"]
        print(f"Success! Distance: {dist:.2f}km, Duration: {dur:.1f}m, Roads: {roads}")
        print(f"Time taken: {t*1000:.1f}ms")
    except RoutingError as e:
        print(f"RoutingError: {e.code} - {e.message}")
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    db = SessionLocal()
    print("Starting integration routes test...")
    
    # 1. Assam (Guwahati to Dispur area)
    test_route(db, "Intra-Assam (Guwahati)", 26.14, 91.74, 26.15, 91.79)
    
    # 2. Manipur (Imphal area)
    test_route(db, "Intra-Manipur (Imphal)", 24.81, 93.93, 24.83, 93.95)
    
    # 3. Meghalaya (Shillong area)
    test_route(db, "Intra-Meghalaya (Shillong)", 25.57, 91.88, 25.59, 91.90)
    
    # 4. Sikkim (Gangtok area)
    test_route(db, "Intra-Sikkim (Gangtok)", 27.32, 88.61, 27.34, 88.62)
    
    # 5. Arunachal Pradesh (Itanagar area)
    test_route(db, "Intra-Arunachal (Itanagar)", 27.10, 93.62, 27.11, 93.64)
    
    # 6. Cross-district (Guwahati to Shillong)
    test_route(db, "Cross-state (Assam -> Meghalaya)", 26.14, 91.74, 25.57, 91.88)
    
    # 7. NO_ROUTE (Guwahati to somewhere random in the ocean or disconnected)
    test_route(db, "Disconnected (Should fail NO_ROUTE)", 26.14, 91.74, -10.0, -10.0)
    
    print("\nIntegration test complete.")
    db.close()

if __name__ == "__main__":
    main()
