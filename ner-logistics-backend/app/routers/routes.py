from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role
from app.services.vehicle_service import haversine_distance_km
from sqlalchemy import text
router = APIRouter(prefix="/routes", tags=["routes"])

@router.post("/", response_model=schemas.RouteOut, status_code=status.HTTP_201_CREATED)
def create_route(
    route: schemas.RouteCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin"))
):
    """Admin only - create a new empty route."""
    db_route = models.Route(**route.model_dump())
    db.add(db_route)
    db.commit()
    db.refresh(db_route)
    return db_route

@router.post("/{route_id}/roads", response_model=schemas.RouteRoadOut, status_code=status.HTTP_201_CREATED)
def add_road_to_route(
    route_id: int,
    route_road: schemas.RouteRoadCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin"))
):
    """Admin only - add an ordered road segment to a route. Enforces 5km geographic continuity."""
    db_route = db.query(models.Route).filter(models.Route.id == route_id).first()
    if not db_route:
        raise HTTPException(status_code=404, detail="Route not found")
        
    db_road = db.query(models.Road).filter(models.Road.id == route_road.road_id).first()
    if not db_road:
        raise HTTPException(status_code=404, detail="Road not found")

    # Fetch previous road in sequence to check connectivity
    prev_route_road = db.query(models.RouteRoad)\
        .filter(models.RouteRoad.route_id == route_id)\
        .order_by(models.RouteRoad.sequence.desc())\
        .first()

    if prev_route_road:
        # Enforce sequence
        if route_road.sequence <= prev_route_road.sequence:
            raise HTTPException(status_code=400, detail="Sequence must be strictly increasing")
            
        prev_road = db.query(models.Road).filter(models.Road.id == prev_route_road.road_id).first()
        if prev_road:
            dist = 999.0
            
            # Geometry-based distance check (PostGIS)
            if prev_road.geometry is not None and db_road.geometry is not None:
                # Get the minimum distance between the two geometries
                # This correctly handles roads that meet at intermediate vertices, not just endpoints
                try:
                    result = db.execute(text("""
                        SELECT ST_Distance(
                            (SELECT geometry::geography FROM roads WHERE id = :prev_id),
                            (SELECT geometry::geography FROM roads WHERE id = :new_id)
                        ) / 1000.0 as dist_km
                    """), {"prev_id": prev_road.id, "new_id": db_road.id}).scalar()
                    if result is not None:
                        dist = result
                except Exception:
                    # Fallback if DB error
                    pass
            
            # Fallback to endpoint Haversine if geometry distance wasn't calculated (e.g. legacy roads)
            if dist == 999.0:
                # Legacy check: Distance from prev_road end to new_road start
                dist = haversine_distance_km(prev_road.end_lat, prev_road.end_lon, db_road.start_lat, db_road.start_lon)
                
            if dist > 5.0:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Disconnected route: Road {db_road.id} starts {dist:.2f}km away from previous Road {prev_road.id} end. Max tolerance is 5km."
                )
    
    db_route_road = models.RouteRoad(
        route_id=route_id,
        road_id=route_road.road_id,
        sequence=route_road.sequence
    )
    db.add(db_route_road)
    db.commit()
    db.refresh(db_route_road)
    return db_route_road
