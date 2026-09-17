from pydantic import BaseModel, field_validator, Field, validator
from typing import Optional, List, Generic, TypeVar, Any, Dict, Literal
from datetime import datetime

# ── Pagination constants ──────────────────────────────────────────────────────
MAX_PAGE_LIMIT = 100
DEFAULT_PAGE_LIMIT = 20

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list response used by all list endpoints."""
    items: List[T]
    total: int
    skip: int
    limit: int


# ── District connectivity schemas ─────────────────────────────────────────────

class DistrictBase(BaseModel):
    id: int
    name: str
    state_id: int
    centroid_lat: Optional[float]
    centroid_lon: Optional[float]
    
    class Config:
        from_attributes = True

class StateBase(BaseModel):
    id: int
    name: str
    districts: List[DistrictBase] = []
    
    class Config:
        from_attributes = True

class RegistryResponse(BaseModel):
    states: List[StateBase]

class RoadCounts(BaseModel):
    total: int
    open: int
    blocked: int
    restricted: int


class BridgeCounts(BaseModel):
    total: int
    good: int
    fair: int
    poor: int
    unverified: int


class DistrictConnectivity(BaseModel):
    district_id: int
    district_name: str
    roads: RoadCounts
    bridges: BridgeCounts




# ── Authentication schemas ────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "field_official"

    @field_validator("role")
    @classmethod
    def role_must_be_field_official(cls, v: str) -> str:
        """Prevent self-registration as admin."""
        if v != "field_official":
            raise ValueError("Only 'field_official' role is allowed during registration")
        return v

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserOut(BaseModel):
    """User response — never exposes password hash."""
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """OAuth2-compatible login: accepts username + password."""
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class RoadBase(BaseModel):
    name: Optional[str] = None
    road_type: Optional[str] = None
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    status: Optional[str] = "open"
    district: Optional[str] = None
    district_id: Optional[int] = None
    geometry: Optional[str] = None


class RoadCreate(RoadBase):
    pass


class RoadOut(RoadBase):
    id: int
    osm_id: Optional[int] = None
    osm_tags: Optional[dict] = None
    is_legacy: Optional[bool] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True

class RoadGeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: Optional[dict] = None
    properties: dict

class RoadGeoJSONCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[RoadGeoJSONFeature]
    total_matched: int


class BridgeBase(BaseModel):
    name: str
    road_id: Optional[int] = None
    latitude: float
    longitude: float
    condition: Optional[str] = "unverified"


class BridgeCreate(BridgeBase):
    pass


class BridgeOut(BridgeBase):
    id: int
    last_verified: Optional[datetime] = None

    class Config:
        from_attributes = True


class IncidentBase(BaseModel):
    incident_type: str
    description: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: Optional[str] = "medium"
    road_id: Optional[int] = None
    bridge_id: Optional[int] = None
    photo_url: Optional[str] = None
    reported_by: Optional[str] = None


class IncidentCreate(IncidentBase):
    pass


class IncidentOut(IncidentBase):
    id: int
    reported_at: datetime
    synced: str
    status: str

    class Config:
        from_attributes = True


class IncidentStatusUpdate(BaseModel):
    status: str
    
    @validator('status')
    def validate_status(cls, v):
        allowed = ["reported", "verified", "resolved"]
        if v not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return v


class IncidentSyncBatchResponse(BaseModel):
    successful_ids: List[int]
    failed_indexes: List[Dict[str, Any]]  # e.g. [{"index": 0, "error": "Invalid latitude"}]


class VehicleBase(BaseModel):
    vehicle_number: str
    cargo_type: Optional[str] = None
    current_lat: float
    current_lon: float
    destination: Optional[str] = None
    speed_kmh: Optional[float] = 0
    status: Optional[str] = "in_transit"
    current_route_id: Optional[int] = None
    current_route_sequence: Optional[int] = None
    current_route_progress_km: Optional[float] = None


class RouteBase(BaseModel):
    name: Optional[str] = None


class RouteCreate(RouteBase):
    pass


class RouteOut(RouteBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RouteRoadBase(BaseModel):
    route_id: int
    road_id: int
    sequence: int
    is_reversed: bool = False
    road_length_km: Optional[float] = None


class RouteRoadCreate(BaseModel):
    road_id: int
    sequence: int
    is_reversed: bool = False
    road_length_km: Optional[float] = None


class RouteRoadOut(RouteRoadBase):
    id: int

    class Config:
        from_attributes = True


class VehicleLocationHistoryOut(BaseModel):
    id: int
    vehicle_id: int
    latitude: float
    longitude: float
    data_source: str
    timestamp: datetime

    class Config:
        from_attributes = True


class VehicleCreate(VehicleBase):
    pass


class VehicleOut(VehicleBase):
    id: int
    updated_at: datetime

    class Config:
        from_attributes = True


class RiskInput(BaseModel):
    road_id: Optional[int] = None
    rainfall_mm: float = 0
    road_condition: str = "good"        # good / fair / poor
    bridge_condition: str = "good"      # good / fair / poor
    recent_incidents: int = 0
    terrain_difficulty: float = 0.3     # 0 (flat/easy) - 1 (very difficult)


class RiskOutput(BaseModel):
    risk_score: float
    risk_level: str
    factors: List[str]
    prediction_source: Literal["ml", "tier1_fallback"] = "tier1_fallback"


class AlertBase(BaseModel):
    alert_type: str
    message_en: str
    message_local: Optional[str] = None
    language: Optional[str] = "en"
    road_id: Optional[int] = None
    bridge_id: Optional[int] = None
    severity: Optional[str] = "medium"


class AlertCreate(AlertBase):
    pass


class AlertOut(AlertBase):
    id: int
    status: Optional[str] = "active"
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Routing schemas ───────────────────────────────────────────────────────────

class RouteRequest(BaseModel):
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lon: float = Field(..., ge=-180, le=180)
    destination_lat: float = Field(..., ge=-90, le=90)
    destination_lon: float = Field(..., ge=-180, le=180)
    preference: Literal["shortest", "safest"] = "shortest"


class RouteResponse(BaseModel):
    """GeoJSON Feature representation of a route."""
    type: str = "Feature"
    geometry: Dict[str, Any]
    properties: Dict[str, Any]
