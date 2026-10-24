import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app import models, schemas
from app.routers.auth import get_current_user

router = APIRouter(prefix="/roads", tags=["roads"])


@router.get("/", response_model=schemas.PaginatedResponse[schemas.RoadOut])
def list_roads(
    district: str | None = Query(None, description="Filter by district name (case-insensitive)"),
    district_id: int | None = Query(None, description="Filter by district ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status: open / blocked / restricted"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(schemas.DEFAULT_PAGE_LIMIT, ge=1, le=schemas.MAX_PAGE_LIMIT, description="Page size"),
    db: Session = Depends(get_db),
):
    """Public — list roads with optional district/status filtering and pagination."""
    query = db.query(models.Road)

    if district is not None:
        query = query.filter(models.Road.district.ilike(district))
    if district_id is not None:
        query = query.filter(models.Road.district_id == district_id)
    if status_filter is not None:
        query = query.filter(models.Road.status.ilike(status_filter))

    total = query.count()
    items = query.order_by(models.Road.id).offset(skip).limit(limit).all()

    return {"items": items, "total": total, "skip": skip, "limit": limit}

@router.get("/bbox", response_model=schemas.RoadGeoJSONCollection)
def get_roads_bbox(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    zoom: int = Query(10, ge=0, le=20),
    district_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(2000, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Get roads within a bounding box, returning GeoJSON Features."""
    
    where_clauses = ["geometry IS NOT NULL", "ST_Intersects(geometry, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"]
    params = {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat, "limit": limit}

    if district_id == -1:
        where_clauses.append("district_id IS NULL")
    elif district_id is not None:
        if zoom < 10:
            where_clauses.append("district_id = :district_id")
            params["district_id"] = district_id
        
    if status_filter:
        where_clauses.append("status ILIKE :status")
        params["status"] = f"%{status_filter}%"

    # Progressive road type filtering by zoom level
    # Shows the connected highway backbone at low zoom, adds detail as user zooms in
    # This ensures the displayed network always looks clean and connected
    if zoom < 10:
        # Show only the main highway backbone — always connected
        where_clauses.append("road_type IN ('trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link')")
    elif zoom < 12:
        # Add tertiary roads — the district-level connector network
        where_clauses.append("road_type IN ('trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link', 'tertiary', 'tertiary_link')")
    elif zoom < 14:
        # Add unclassified roads — rural connectors
        where_clauses.append("road_type NOT IN ('residential', 'service')")
    # zoom >= 14: show ALL road types including residential

    where_sql = " AND ".join(where_clauses)
    
    # Fast indexed ordering — prioritize major roads first
    order_sql = "CASE road_type WHEN 'trunk' THEN 1 WHEN 'primary' THEN 2 WHEN 'secondary' THEN 3 WHEN 'tertiary' THEN 4 ELSE 5 END, id ASC"

    # Simplification logic for zoom levels
    if zoom < 8:
        return {"type": "FeatureCollection", "features": [], "total_matched": 0}
    elif zoom < 10:
        geom_sql = "ST_AsGeoJSON(ST_Simplify(geometry, 0.005)) as geojson"
    elif zoom < 12:
        geom_sql = "ST_AsGeoJSON(ST_Simplify(geometry, 0.001)) as geojson"
    else:
        geom_sql = "ST_AsGeoJSON(geometry) as geojson"

    query_sql = text(f"""
        SELECT 
            id, name, road_type, status, district_id, osm_id,
            {geom_sql}
        FROM roads
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT :limit
    """)

    results = db.execute(query_sql, params).fetchall()
    total_matched = len(results)
    
    features = []
    for row in results:
        properties = {
            "id": row.id,
            "name": row.name,
            "road_type": row.road_type,
            "status": row.status,
            "district_id": row.district_id,
            "osm_id": row.osm_id
        }
        geom = json.loads(row.geojson) if row.geojson else None
        
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": properties
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "total_matched": total_matched
    }



@router.post("/", response_model=schemas.RoadOut, status_code=status.HTTP_201_CREATED)
def create_road(
    road: schemas.RoadCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Admin/Field Official — Create a new road."""
    db_road = models.Road(**road.model_dump())
    db.add(db_road)
    db.commit()
    db.refresh(db_road)
    return db_road


@router.get("/{road_id}", response_model=schemas.RoadOut)
def get_road(road_id: int, db: Session = Depends(get_db)):
    road = db.query(models.Road).filter(models.Road.id == road_id).first()
    if road is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Road with id {road_id} not found",
        )
    return road
