import os
import uuid
import shutil
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role

router = APIRouter(prefix="/incidents", tags=["incidents"])

@router.get("/", response_model=schemas.PaginatedResponse[schemas.IncidentOut])
def list_incidents(
    incident_type: str | None = Query(None, description="Filter by incident type"),
    severity: str | None = Query(None, description="Filter by severity: low / medium / high"),
    road_id: int | None = Query(None, description="Filter by road ID"),
    bridge_id: int | None = Query(None, description="Filter by bridge ID"),
    incident_status: str | None = Query(None, alias="status", description="Filter by status: reported / verified / resolved"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(schemas.DEFAULT_PAGE_LIMIT, ge=1, le=schemas.MAX_PAGE_LIMIT, description="Page size"),
    db: Session = Depends(get_db),
):
    """Public — GIS dashboard needs unauthenticated read access."""
    query = db.query(models.Incident)

    if incident_type is not None:
        query = query.filter(models.Incident.incident_type.ilike(incident_type))
    if severity is not None:
        query = query.filter(models.Incident.severity.ilike(severity))
    if road_id is not None:
        query = query.filter(models.Incident.road_id == road_id)
    if bridge_id is not None:
        query = query.filter(models.Incident.bridge_id == bridge_id)
    if incident_status is not None:
        query = query.filter(models.Incident.status.ilike(incident_status))
    if start_date is not None:
        query = query.filter(models.Incident.reported_at >= start_date)
    if end_date is not None:
        query = query.filter(models.Incident.reported_at <= end_date)

    total = query.count()
    items = query.order_by(models.Incident.reported_at.desc()).offset(skip).limit(limit).all()

    return {"items": items, "total": total, "skip": skip, "limit": limit}

@router.post("/sync-batch", response_model=schemas.IncidentSyncBatchResponse)
def sync_incidents_batch(
    incidents: List[schemas.IncidentCreate],
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("field_official", "admin")),
):
    """
    Offline batch synchronization.
    Accepts a list of incidents, validates and saves them, returning partial success info.
    """
    successful_ids = []
    failed_indexes = []

    for idx, inc_data in enumerate(incidents):
        try:
            # Validate FKs
            if inc_data.road_id is not None:
                road = db.query(models.Road).filter(models.Road.id == inc_data.road_id).first()
                if not road:
                    failed_indexes.append({"index": idx, "error": f"Road {inc_data.road_id} not found"})
                    continue
            
            if inc_data.bridge_id is not None:
                bridge = db.query(models.Bridge).filter(models.Bridge.id == inc_data.bridge_id).first()
                if not bridge:
                    failed_indexes.append({"index": idx, "error": f"Bridge {inc_data.bridge_id} not found"})
                    continue

            db_incident = models.Incident(
                **inc_data.model_dump(),
                status="reported",
                synced="synced"
            )
            db.add(db_incident)
            db.commit()
            db.refresh(db_incident)
            successful_ids.append(db_incident.id)
            
        except Exception as e:
            db.rollback()
            failed_indexes.append({"index": idx, "error": str(e)})

    return {"successful_ids": successful_ids, "failed_indexes": failed_indexes}

@router.post("/", response_model=schemas.IncidentOut)
def create_incident(
    incident: schemas.IncidentCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("field_official", "admin")),
):
    """
    Submit a single incident.
    """
    if incident.road_id is not None:
        road = db.query(models.Road).filter(models.Road.id == incident.road_id).first()
        if not road:
            raise HTTPException(status_code=400, detail=f"Road {incident.road_id} not found")
    
    if incident.bridge_id is not None:
        bridge = db.query(models.Bridge).filter(models.Bridge.id == incident.bridge_id).first()
        if not bridge:
            raise HTTPException(status_code=400, detail=f"Bridge {incident.bridge_id} not found")

    db_incident = models.Incident(
        **incident.model_dump(),
        status="reported",
        synced="synced"
    )
    db.add(db_incident)
    db.commit()
    db.refresh(db_incident)
    return db_incident


@router.patch("/{incident_id}/status", response_model=schemas.IncidentOut)
def update_incident_status(
    incident_id: int,
    payload: schemas.IncidentStatusUpdate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("field_official", "admin")),
):
    """
    Update lifecycle status (reported -> verified -> resolved).
    """
    db_incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not db_incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    current = db_incident.status
    target = payload.status

    # Validate transitions
    valid_transitions = {
        "reported": ["verified"],
        "verified": ["resolved"],
        "resolved": []
    }

    if target not in valid_transitions.get(current, []):
        raise HTTPException(status_code=400, detail=f"Invalid transition from {current} to {target}")

    db_incident.status = target
    db.commit()
    db.refresh(db_incident)
    return db_incident


@router.post("/{incident_id}/photo", response_model=schemas.IncidentOut)
def upload_incident_photo(
    incident_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("field_official", "admin")),
):
    """
    Upload a real photo to local storage (Development only).
    """
    db_incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not db_incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > 5 * 1024 * 1024: # 5 MB
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    os.makedirs("media", exist_ok=True)
    
    # Security: Path traversal & extension validation
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    
    base = os.path.basename(file.filename or "default.jpg")
    ext = os.path.splitext(base)[1].lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid image extension. Only JPG, PNG, WEBP allowed.")

    safe_filename = f"incident_{incident_id}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join("media", safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_incident.photo_url = f"/media/{safe_filename}"
    db.commit()
    db.refresh(db_incident)
    return db_incident
