from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role

router = APIRouter(prefix="/bridges", tags=["bridges"])


@router.get("/", response_model=schemas.PaginatedResponse[schemas.BridgeOut])
def list_bridges(
    road_id: int | None = Query(None, description="Filter by road_id"),
    condition: str | None = Query(None, description="Filter by condition: good / fair / poor / unverified"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(schemas.DEFAULT_PAGE_LIMIT, ge=1, le=schemas.MAX_PAGE_LIMIT, description="Page size"),
    db: Session = Depends(get_db),
):
    """Public — list bridges with optional filtering and pagination."""
    query = db.query(models.Bridge)

    if road_id is not None:
        query = query.filter(models.Bridge.road_id == road_id)
    if condition is not None:
        query = query.filter(models.Bridge.condition.ilike(condition))

    total = query.count()
    items = query.order_by(models.Bridge.id).offset(skip).limit(limit).all()

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{bridge_id}", response_model=schemas.BridgeOut)
def get_bridge(bridge_id: int, db: Session = Depends(get_db)):
    """Public — get a single bridge by ID."""
    bridge = db.query(models.Bridge).filter(models.Bridge.id == bridge_id).first()
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bridge with id {bridge_id} not found",
        )
    return bridge


@router.post("/", response_model=schemas.BridgeOut, status_code=status.HTTP_201_CREATED)
def create_bridge(
    bridge: schemas.BridgeCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin")),
):
    """Admin only — create a new bridge record.

    If road_id is provided, validates that the referenced Road exists.
    """
    if bridge.road_id is not None:
        road = db.query(models.Road).filter(models.Road.id == bridge.road_id).first()
        if road is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Road with id {bridge.road_id} not found — cannot create bridge with invalid road_id",
            )

    db_bridge = models.Bridge(**bridge.model_dump())
    db.add(db_bridge)
    db.commit()
    db.refresh(db_bridge)
    return db_bridge


@router.patch("/{bridge_id}/condition", response_model=schemas.BridgeOut)
def update_bridge_condition(
    bridge_id: int,
    condition: str,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("field_official", "admin")),
):
    """Field officials update bridge status from here -- this is your
    replacement for the official bridge-condition dataset that doesn't exist.

    Automatically sets last_verified to the current UTC time.
    """
    bridge = db.query(models.Bridge).filter(models.Bridge.id == bridge_id).first()
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bridge with id {bridge_id} not found",
        )

    bridge.condition = condition
    bridge.last_verified = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bridge)
    return bridge
