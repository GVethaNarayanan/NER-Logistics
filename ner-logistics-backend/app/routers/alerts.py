from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Starter translation table for the multilingual-notifications requirement.
# Replace these placeholder strings with verified translations, and extend
# properly on the frontend with i18next for the full UI.
TRANSLATIONS = {
    "as": {"high_risk": "সাৱধান: এই পথত বিপদৰ আশংকা বেছি"},   # Assamese - verify wording
    "hi": {"high_risk": "चेतावनी: इस मार्ग पर उच्च जोखिम है"},
}


@router.get("/", response_model=schemas.PaginatedResponse[schemas.AlertOut])
def list_alerts(
    alert_type: str | None = Query(None, description="Filter by alert type"),
    severity: str | None = Query(None, description="Filter by severity"),
    status: str | None = Query(None, description="Filter by status (active/resolved)"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(schemas.DEFAULT_PAGE_LIMIT, ge=1, le=schemas.MAX_PAGE_LIMIT, description="Page size"),
    db: Session = Depends(get_db),
):
    """Public — GIS dashboard needs unauthenticated read access."""
    query = db.query(models.Alert)

    if alert_type is not None:
        query = query.filter(models.Alert.alert_type.ilike(alert_type))
    if severity is not None:
        query = query.filter(models.Alert.severity.ilike(severity))
    if status is not None:
        query = query.filter(models.Alert.status.ilike(status))

    total = query.count()
    items = query.order_by(models.Alert.created_at.desc()).offset(skip).limit(limit).all()

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=schemas.AlertOut)
def create_alert(
    alert: schemas.AlertCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_role("admin")),
):
    """Admin only — manually create an alert."""
    data = alert.model_dump()
    if not data.get("message_local") and data.get("language") in TRANSLATIONS:
        data["message_local"] = TRANSLATIONS[data["language"]].get(data["alert_type"])
    db_alert = models.Alert(**data)
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert
