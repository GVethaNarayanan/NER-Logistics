from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import schemas
from app.services.routing_service import find_route, RoutingError
from app.services.graph_service import get_graph_diagnostics

router = APIRouter(prefix="/routing", tags=["routing"])

@router.get("/diagnostics")
def routing_diagnostics():
    """Return diagnostic information about the routing graph cache."""
    return get_graph_diagnostics()

@router.post("/route", response_model=schemas.RouteResponse)
def compute_route(
    request: schemas.RouteRequest,
    db: Session = Depends(get_db)
):
    """
    Public — calculate a shortest-path route between arbitrary coordinates.
    
    Snaps origin and destination to the nearest road edges, then computes
    the optimal path using Haversine distance weights.
    
    Returns a GeoJSON Feature containing a LineString geometry and metadata.
    """
    try:
        route_geojson = find_route(
            db=db,
            origin_lat=request.origin_lat,
            origin_lon=request.origin_lon,
            dest_lat=request.destination_lat,
            dest_lon=request.destination_lon,
            preference=request.preference,
        )
        return route_geojson
    except RoutingError as e:
        # Route logic specifically raises 400 for its domain errors:
        # ROUTING_DATA_UNAVAILABLE, SNAP_FAILED, NO_ROUTE
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{e.code}: {e.message}"
        )
