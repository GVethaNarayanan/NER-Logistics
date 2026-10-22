import os
import sys

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models import Vehicle, Route, RouteRoad
from app.services.routing_service import find_route

def dispatch_trucks():
    db = SessionLocal()
    
    # Target destinations for the trucks
    destinations = [
        {"name": "VH-1001", "lat": 25.5788, "lon": 91.8933},  # Shillong
        {"name": "VH-1002", "lat": 26.6528, "lon": 92.7926},  # Tezpur
    ]
    
    try:
        for dest in destinations:
            vehicle = db.query(Vehicle).filter(Vehicle.vehicle_number == dest["name"]).first()
            if not vehicle:
                print(f"Vehicle {dest['name']} not found.")
                continue
                
            print(f"\nCalculating route for {dest['name']} from ({vehicle.current_lat}, {vehicle.current_lon}) to ({dest['lat']}, {dest['lon']})...")
            
            # Find the route using the loaded graph
            res = find_route(db, vehicle.current_lat, vehicle.current_lon, dest["lat"], dest["lon"], preference="shortest")
            
            if "error" in res:
                print(f"Failed to route {dest['name']}: {res['error']}")
                continue
                
            # 1. Create a Saved Route
            route_name = f"Auto-Dispatch: {dest['name']} Delivery"
            route = Route(name=route_name)
            db.add(route)
            db.commit()
            
            # 2. Add all roads to the sequence
            print(f"Assigning {len(res['path'])} roads to route {route.id}...")
            seq = 1
            for step in res["path"]:
                rr = RouteRoad(
                    route_id=route.id,
                    road_id=step["road_id"],
                    sequence=seq,
                    is_reversed=step.get("is_reversed", False),
                    road_length_km=step.get("distance_km", 0.1)
                )
                db.add(rr)
                seq += 1
            db.commit()
            
            # 3. Assign route to vehicle and set it moving
            vehicle.current_route_id = route.id
            vehicle.current_route_sequence = 1
            vehicle.current_route_progress_km = 0.0
            vehicle.status = "in_transit"
            vehicle.speed_kmh = 60.0  # Move at 60 km/h
            
            db.commit()
            print(f"Successfully dispatched {dest['name']}!")
            
    finally:
        db.close()

if __name__ == "__main__":
    dispatch_trucks()
