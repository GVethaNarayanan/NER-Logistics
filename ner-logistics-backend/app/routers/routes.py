from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role
from app.routers.auth import get_current_user
from app.services.vehicle_service import haversine_distance_km
from sqlalchemy import text
router = APIRouter(prefix="/routes", tags=["routes"])


# ── Public READ endpoints (all logged-in users can view saved routes) ────────

@router.get("/")
def list_routes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Public — list all saved routes. Any user can view."""
    total = db.query(models.Route).count()
    routes = db.query(models.Route).order_by(models.Route.id.desc()).offset(skip).limit(limit).all()
    
    result = []
    for route in routes:
        route_roads = db.query(models.RouteRoad).filter(
            models.RouteRoad.route_id == route.id
        ).order_by(models.RouteRoad.sequence).all()
        
        total_distance = sum(rr.road_length_km or 0 for rr in route_roads)
        
        result.append({
            "id": route.id,
            "name": route.name,
            "road_count": len(route_roads),
            "total_distance_km": round(total_distance, 2),
            "created_at": route.created_at.isoformat() if hasattr(route, 'created_at') and route.created_at else None,
        })
    
    return {"items": result, "total": total, "skip": skip, "limit": limit}


@router.get("/{route_id}")
def get_route_detail(
    route_id: int,
    db: Session = Depends(get_db),
):
    """Public — get a single route with all its road segments."""
    route = db.query(models.Route).filter(models.Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    
    route_roads = db.query(models.RouteRoad).filter(
        models.RouteRoad.route_id == route_id
    ).order_by(models.RouteRoad.sequence).all()
    
    segments = []
    for rr in route_roads:
        road = db.query(models.Road).filter(models.Road.id == rr.road_id).first()
        segments.append({
            "id": rr.id,
            "sequence": rr.sequence,
            "road_id": rr.road_id,
            "road_name": road.name if road else None,
            "road_type": road.road_type if road else None,
            "road_status": road.status if road else None,
            "road_length_km": rr.road_length_km,
            "is_reversed": rr.is_reversed,
        })
    
    blocked_roads = [s for s in segments if s.get("road_status") == "blocked"]
    restricted_roads = [s for s in segments if s.get("road_status") == "restricted"]
    
    if blocked_roads:
        route_status = "blocked"
    elif restricted_roads:
        route_status = "restricted"
    else:
        route_status = "open"
    
    return {
        "id": route.id,
        "name": route.name,
        "route_status": route_status,
        "blocked_road_count": len(blocked_roads),
        "restricted_road_count": len(restricted_roads),
        "segments": segments,
        "total_distance_km": round(sum(s.get("road_length_km") or 0 for s in segments), 2),
    }


# ── Admin-only WRITE endpoints ──────────────────────────────────────────────

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
        if route_road.sequence <= prev_route_road.sequence:
            raise HTTPException(status_code=400, detail="Sequence must be strictly increasing")
            
        prev_road = db.query(models.Road).filter(models.Road.id == prev_route_road.road_id).first()
        if prev_road:
            dist = 999.0
            
            if prev_road.geometry is not None and db_road.geometry is not None:
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
                    pass
            
            if dist == 999.0:
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


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin"))
):
    """Admin only - delete a saved route."""
    route = db.query(models.Route).filter(models.Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    
    db.query(models.RouteRoad).filter(models.RouteRoad.route_id == route_id).delete()
    db.delete(route)
    db.commit()
