import math
from sqlalchemy.orm import Session
from app import models

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def update_vehicle_location(db: Session, vehicle: models.Vehicle, lat: float, lon: float, data_source: str = "manual"):
    vehicle.current_lat = lat
    vehicle.current_lon = lon
    
    history_entry = models.VehicleLocationHistory(
        vehicle_id=vehicle.id,
        latitude=lat,
        longitude=lon,
        data_source=data_source
    )
    db.add(history_entry)
    # The caller is responsible for db.commit() to ensure atomicity.
    return vehicle

from sqlalchemy import text
from typing import Dict, Any, Optional

def locate_vehicle_context(db: Session, lat: float, lon: float) -> Dict[str, Any]:
    """
    Use PostGIS to find the nearest road (within 100m) and the containing district.
    Never fabricates a district. If the point falls outside authentic boundaries, district is None.
    """
    result = {
        "road_id": None,
        "road_name": None,
        "district_id": None,
        "district_name": None,
        "state_name": None
    }
    
    # Nearest road (within 100m)
    road_query = text("""
        SELECT id, name
        FROM roads
        WHERE ST_DWithin(geometry::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 100)
        ORDER BY geometry <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
        LIMIT 1
    """)
    road_row = db.execute(road_query, {"lat": lat, "lon": lon}).fetchone()
    if road_row:
        result["road_id"] = road_row[0]
        result["road_name"] = road_row[1]
        
    # Containing district
    dist_query = text("""
        SELECT d.id, d.name, s.name as state_name
        FROM districts d
        JOIN states s ON d.state_id = s.id
        WHERE ST_Contains(d.boundary, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
        LIMIT 1
    """)
    dist_row = db.execute(dist_query, {"lat": lat, "lon": lon}).fetchone()
    if dist_row:
        result["district_id"] = dist_row[0]
        result["district_name"] = dist_row[1]
        result["state_name"] = dist_row[2]
        
    return result
