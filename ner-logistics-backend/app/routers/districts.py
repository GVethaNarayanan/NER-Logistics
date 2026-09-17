"""
District connectivity endpoint — SIH26002 requires district-wise
connectivity information computed from actual database records.

All values are aggregated from the roads and bridges tables.
Nothing is hard-coded or fabricated.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/districts", tags=["districts"])

@router.get("/registry", response_model=schemas.RegistryResponse)
def get_district_registry(db: Session = Depends(get_db)):
    """Public — returns canonical registry of states and districts."""
    states = db.query(models.State).options(joinedload(models.State.districts)).all()
    return schemas.RegistryResponse(states=states)


import json
from sqlalchemy import text

@router.get(
    "/{district_id:int}/connectivity",
    response_model=schemas.DistrictConnectivity,
)
def get_district_connectivity(
    district_id: int,
    db: Session = Depends(get_db),
):
    """Public — returns district-wise road/bridge connectivity summary via FK."""
    district = db.query(models.District).filter(models.District.id == district_id).first()
    if not district:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"District with ID '{district_id}' not found",
        )

    # ── Road counts (aggregated from roads table) ─────────────────────────
    road_query = db.query(models.Road).filter(
        models.Road.district_id == district_id
    )
    total_roads = road_query.count()

    # Count by status using DB aggregation
    road_status_counts = (
        db.query(
            func.lower(models.Road.status).label("status"),
            func.count().label("cnt"),
        )
        .filter(models.Road.district_id == district_id)
        .group_by(func.lower(models.Road.status))
        .all()
    )
    road_status_map = {row.status: row.cnt for row in road_status_counts}

    roads = schemas.RoadCounts(
        total=total_roads,
        open=road_status_map.get("open", 0),
        blocked=road_status_map.get("blocked", 0),
        restricted=road_status_map.get("restricted", 0),
    )

    # ── Bridge counts (bridges linked to roads in this district) ──────────
    bridge_query = (
        db.query(models.Bridge)
        .join(models.Road, models.Bridge.road_id == models.Road.id)
        .filter(models.Road.district_id == district_id)
    )
    total_bridges = bridge_query.count()

    bridge_cond_counts = (
        db.query(
            func.lower(models.Bridge.condition).label("condition"),
            func.count().label("cnt"),
        )
        .join(models.Road, models.Bridge.road_id == models.Road.id)
        .filter(models.Road.district_id == district_id)
        .group_by(func.lower(models.Bridge.condition))
        .all()
    )
    bridge_cond_map = {row.condition: row.cnt for row in bridge_cond_counts}

    bridges = schemas.BridgeCounts(
        total=total_bridges,
        good=bridge_cond_map.get("good", 0),
        fair=bridge_cond_map.get("fair", 0),
        poor=bridge_cond_map.get("poor", 0),
        unverified=bridge_cond_map.get("unverified", 0),
    )

    return schemas.DistrictConnectivity(
        district_id=district_id,
        district_name=district.name,
        roads=roads,
        bridges=bridges,
    )


@router.get(
    "/{district_name:str}/connectivity",
    response_model=schemas.DistrictConnectivity,
    deprecated=True
)
def get_district_connectivity_legacy(
    district_name: str,
    db: Session = Depends(get_db),
):
    """Deprecated alias for backward compatibility."""
    district = db.query(models.District).filter(models.District.name.ilike(district_name)).first()
    if not district:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"District '{district_name}' not found",
        )
    return get_district_connectivity(district_id=district.id, db=db)


@router.get("/locate")
def locate_district(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
):
    """Resolve a lat/lon point to the containing district using spatial containment."""
    result = db.execute(text("""
        SELECT id, name, state_id
        FROM districts
        WHERE boundary IS NOT NULL
          AND ST_Contains(boundary, ST_SetSRID(ST_Point(:lon, :lat), 4326))
        LIMIT 1
    """), {"lat": lat, "lon": lon}).fetchone()
    
    if not result:
        return {"district": None, "message": "Point is outside all known district boundaries"}
    
    return {"district_id": result.id, "district_name": result.name, "state_id": result.state_id}


@router.get("/{district_id:int}/boundary")
def get_district_boundary(district_id: int, db: Session = Depends(get_db)):
    """Return district boundary as GeoJSON for map rendering."""
    result = db.execute(text("""
        SELECT ST_AsGeoJSON(boundary) as geojson
        FROM districts
        WHERE id = :district_id AND boundary IS NOT NULL
    """), {"district_id": district_id}).fetchone()
    
    if not result:
        raise HTTPException(404, detail="District boundary not available")
    
    return {"type": "Feature", "geometry": json.loads(result.geojson), "properties": {"district_id": district_id}}

