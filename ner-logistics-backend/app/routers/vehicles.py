from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/", response_model=schemas.PaginatedResponse[schemas.VehicleOut])
def list_vehicles(
    vehicle_status: str | None = Query(None, alias="status", description="Filter by status: in_transit / delivered / idle"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(schemas.DEFAULT_PAGE_LIMIT, ge=1, le=schemas.MAX_PAGE_LIMIT, description="Page size"),
    db: Session = Depends(get_db),
):
    """Public — GIS dashboard needs unauthenticated read access."""
    query = db.query(models.Vehicle)

    if vehicle_status is not None:
        query = query.filter(models.Vehicle.status.ilike(vehicle_status))

    total = query.count()
    items = query.order_by(models.Vehicle.id).offset(skip).limit(limit).all()

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=schemas.VehicleOut)
def create_vehicle(
    vehicle: schemas.VehicleCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin")),
):
    """Admin only — register a new vehicle."""
    db_vehicle = models.Vehicle(**vehicle.model_dump())
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle


from app.services.vehicle_service import update_vehicle_location
from app.services.routing_service import find_route, create_route_from_computed, RoutingError

@router.patch("/{vehicle_id}/location", response_model=schemas.VehicleOut)
def update_location(
    vehicle_id: int,
    lat: float,
    lon: float,
    speed_kmh: float = 0,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("field_official", "admin")),
):
    """Called by field app or manually to move a vehicle."""
    vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with id {vehicle_id} not found",
        )
    
    vehicle.speed_kmh = speed_kmh
    # Uses service to insert history automatically
    update_vehicle_location(db, vehicle, lat, lon, data_source="manual")
    db.commit()
    db.refresh(vehicle)
    return vehicle

@router.patch("/{vehicle_id}/route", response_model=schemas.VehicleOut)
def assign_route(
    vehicle_id: int,
    route_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin"))
):
    """Assign an ordered route to a vehicle and reset its route progress."""
    vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
        
    route = db.query(models.Route).filter(models.Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
        
    vehicle.current_route_id = route_id
    vehicle.current_route_sequence = 0
    vehicle.current_route_progress_km = 0.0
    db.commit()
    db.refresh(vehicle)
    return vehicle

@router.post("/{vehicle_id}/dispatch", response_model=schemas.VehicleOut)
def dispatch_vehicle(
    vehicle_id: int,
    request: schemas.RouteRequest,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin"))
):
    """Compute a route and assign it to a vehicle, setting status to in_transit."""
    vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
        
    try:
        route_geojson = find_route(
            db=db,
            origin_lat=request.origin_lat,
            origin_lon=request.origin_lon,
            dest_lat=request.destination_lat,
            dest_lon=request.destination_lon,
            preference=request.preference,
        )
    except RoutingError as e:
        raise HTTPException(status_code=400, detail=str(e.message))

    # Create the route in DB
    name = f"Route for {vehicle.vehicle_number}"
    db_route = create_route_from_computed(db, route_geojson, name)
    
    # Assign and dispatch
    vehicle.current_route_id = db_route.id
    vehicle.current_route_sequence = 0
    vehicle.current_route_progress_km = 0.0
    vehicle.status = "in_transit"
    if vehicle.speed_kmh <= 0:
        vehicle.speed_kmh = 40.0  # default dispatch speed
        
    # Snap initial location to route origin
    origin = route_geojson["properties"]["snapped_origin"]
    update_vehicle_location(db, vehicle, origin["lat"], origin["lon"], "dispatch")
    
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}/history", response_model=schemas.PaginatedResponse[schemas.VehicleLocationHistoryOut])
def get_vehicle_history(
    vehicle_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(schemas.DEFAULT_PAGE_LIMIT, ge=1, le=schemas.MAX_PAGE_LIMIT),
    db: Session = Depends(get_db)
):
    """Public access to view vehicle trails chronologically."""
    vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
        
    query = db.query(models.VehicleLocationHistory).filter(models.VehicleLocationHistory.vehicle_id == vehicle_id).order_by(models.VehicleLocationHistory.timestamp.asc())
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    
    return {"items": items, "total": total, "skip": skip, "limit": limit}
