import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
from app.services.vehicle_service import update_vehicle_location, haversine_distance_km

logger = logging.getLogger(__name__)

SIMULATION_INTERVAL_SECONDS = 10

from geoalchemy2.shape import to_shape
import shapely.wkt
from sqlalchemy import text

def interpolate_linestring(wkt_geom: str, progress_km: float, total_length_km: float, is_reversed: bool) -> tuple[float, float]:
    """Interpolate position along a LineString geometry using Shapely."""
    try:
        geom = shapely.wkt.loads(wkt_geom)
        if is_reversed:
            # Shapely geometry reverse
            coords = list(geom.coords)[::-1]
            geom = shapely.geometry.LineString(coords)
            
        # fraction of total length
        fraction = min(1.0, max(0.0, progress_km / total_length_km)) if total_length_km > 0 else 1.0
        
        # interpolate on normalized line (0.0 to 1.0 length)
        point = geom.interpolate(fraction, normalized=True)
        return point.y, point.x  # returns lat, lon
    except Exception as e:
        logger.error(f"Error interpolating geometry: {e}")
        return 0.0, 0.0

def run_vehicle_simulation(db: Session = None, loop_fleet: bool = None):
    """Background job that advances in-transit vehicles along their assigned routes."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        if loop_fleet is None:
            loop_fleet = True
    elif loop_fleet is None:
        loop_fleet = False
        
    try:
        query = db.query(models.Vehicle).filter(
            models.Vehicle.current_route_id.isnot(None),
            models.Vehicle.speed_kmh > 0
        )
        if not loop_fleet:
            query = query.filter(models.Vehicle.status == "in_transit")
            
        active_vehicles = query.all()
        
        for vehicle in active_vehicles:
            try:
                # 1. Fetch current route road sequence
                route_roads = db.query(models.RouteRoad)\
                    .filter(models.RouteRoad.route_id == vehicle.current_route_id)\
                    .order_by(models.RouteRoad.sequence.asc())\
                    .all()
                
                if not route_roads:
                    continue  # Route has no roads
                    
                current_seq_idx = vehicle.current_route_sequence or 0
                
                if current_seq_idx >= len(route_roads):
                    if loop_fleet:
                        # Loop route for continuous live fleet simulation
                        vehicle.status = "in_transit"
                        vehicle.current_route_sequence = 0
                        vehicle.current_route_progress_km = 0.0
                        current_seq_idx = 0
                    else:
                        vehicle.status = "delivered"
                        db.commit()
                        continue
                    
                current_route_road = route_roads[current_seq_idx]
                road = db.query(models.Road).filter(models.Road.id == current_route_road.road_id).first()
                if not road:
                    continue
                    
                # 2. Calculate step distance
                distance_km = vehicle.speed_kmh * (SIMULATION_INTERVAL_SECONDS / 3600.0)
                
                # 3. Advance progress
                progress_km = (vehicle.current_route_progress_km or 0.0) + distance_km
                
                # 4. Determine road length
                road_length_km = current_route_road.road_length_km
                if road_length_km is None or road_length_km <= 0:
                    road_length_km = haversine_distance_km(road.start_lat, road.start_lon, road.end_lat, road.end_lon)
                
                # Fetch WKT geometry with safe fallback for SQLite test environments
                wkt_geom = None
                try:
                    wkt_geom = db.execute(text("SELECT ST_AsText(geometry) FROM roads WHERE id = :id"), {"id": road.id}).scalar()
                except Exception:
                    pass
                if not wkt_geom:
                    wkt_geom = f"LINESTRING({road.start_lon} {road.start_lat}, {road.end_lon} {road.end_lat})"
                
                if road_length_km <= 0.001:
                    vehicle.current_route_sequence = (vehicle.current_route_sequence or 0) + 1
                    vehicle.current_route_progress_km = 0.0
                    if vehicle.current_route_sequence >= len(route_roads):
                        if loop_fleet:
                            vehicle.current_route_sequence = 0
                            vehicle.status = "in_transit"
                        else:
                            vehicle.status = "delivered"
                    update_vehicle_location(db, vehicle, road.end_lat, road.end_lon, data_source="simulated")
                elif progress_km >= road_length_km:
                    # Vehicle has reached or passed the end of this road segment
                    vehicle.current_route_sequence = (vehicle.current_route_sequence or 0) + 1
                    vehicle.current_route_progress_km = 0.0
                    
                    # Snap precisely to end of the road to avoid drift
                    end_lat, end_lon = interpolate_linestring(wkt_geom, road_length_km, road_length_km, current_route_road.is_reversed)
                    update_vehicle_location(db, vehicle, end_lat, end_lon, data_source="simulated")
                    
                    if vehicle.current_route_sequence >= len(route_roads):
                        if loop_fleet:
                            vehicle.current_route_sequence = 0
                            vehicle.status = "in_transit"
                        else:
                            vehicle.status = "delivered"
                else:
                    # Interpolate location along the current road geometry
                    new_lat, new_lon = interpolate_linestring(wkt_geom, progress_km, road_length_km, current_route_road.is_reversed)
                    vehicle.current_route_progress_km = progress_km
                    update_vehicle_location(db, vehicle, new_lat, new_lon, data_source="simulated")
                
                db.commit()
                
            except Exception as e:
                logger.error(f"Error simulating vehicle {vehicle.id}: {e}")
                db.rollback()
                
    except Exception as e:
        logger.error(f"Vehicle simulation job failed: {e}")
    finally:
        if close_db:
            db.close()
