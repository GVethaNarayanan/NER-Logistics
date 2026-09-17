from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, BigInteger, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.spatial_types import FlexibleGeometry

# ── Valid roles (referenced by auth_service and dependencies) ─────────────────
VALID_ROLES = {"field_official", "admin"}


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="field_official", nullable=False)  # field_official / admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class State(Base):
    __tablename__ = "states"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    boundary = Column(FlexibleGeometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True)
    districts = relationship("District", back_populates="state")


class District(Base):
    __tablename__ = "districts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=False)
    boundary = Column(FlexibleGeometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True)
    centroid_lat = Column(Float, nullable=True)
    centroid_lon = Column(Float, nullable=True)
    
    state = relationship("State", back_populates="districts")
    roads = relationship("Road", back_populates="district_rel")


class Road(Base):
    __tablename__ = "roads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    road_type = Column(String)
    start_lat = Column(Float)
    start_lon = Column(Float)
    end_lat = Column(Float)
    end_lon = Column(Float)
    geometry = Column(FlexibleGeometry(geometry_type="LINESTRING", srid=4326), nullable=True)
    status = Column(String, default="open")  # open / blocked / restricted
    district = Column(String, index=True)    # legacy string
    district_id = Column(Integer, ForeignKey("districts.id"), index=True, nullable=True)
    
    osm_id = Column(BigInteger, unique=True, index=True, nullable=True)
    osm_tags = Column(JSON, nullable=True)
    source = Column(String, default="osm")
    is_legacy = Column(Boolean, default=False)
    
    district_rel = relationship("District", back_populates="roads")


class Bridge(Base):
    __tablename__ = "bridges"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=True)
    latitude = Column(Float)
    longitude = Column(Float)
    condition = Column(String, default="unverified")  # good / fair / poor / unverified
    last_verified = Column(DateTime, nullable=True)


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    recorded_at = Column(DateTime, server_default=func.now())
    rainfall_mm = Column(Float, default=0)
    temperature_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    wind_speed_kmh = Column(Float, nullable=True)
    condition = Column(String, nullable=True)
    data_source = Column(String, default="verified")


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True, index=True)
    incident_type = Column(String)  # landslide / flood / road_damage / accident / other
    description = Column(Text, nullable=True)
    latitude = Column(Float)
    longitude = Column(Float)
    severity = Column(String, default="medium")  # low / medium / high
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=True)
    bridge_id = Column(Integer, ForeignKey("bridges.id"), nullable=True)
    photo_url = Column(String, nullable=True)
    reported_by = Column(String, nullable=True)
    reported_at = Column(DateTime, server_default=func.now())
    synced = Column(String, default="synced")  # synced / pending -> offline queue tracking
    status = Column(String, default="reported")  # reported / verified / resolved


class Route(Base):
    __tablename__ = "routes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    created_at = Column(DateTime, server_default=func.now())


class RouteRoad(Base):
    __tablename__ = "route_roads"
    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    is_reversed = Column(Boolean, nullable=False, default=False)
    road_length_km = Column(Float, nullable=True)


class VehicleLocationHistory(Base):
    __tablename__ = "vehicle_location_history"
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    data_source = Column(String, default="simulated")
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, index=True)
    vehicle_number = Column(String, index=True)
    cargo_type = Column(String, nullable=True)  # medicine / food / construction / agriculture
    current_lat = Column(Float)
    current_lon = Column(Float)
    destination = Column(String, nullable=True)
    speed_kmh = Column(Float, default=0)
    status = Column(String, default="in_transit")  # in_transit / delivered / idle
    eta = Column(DateTime, nullable=True)
    current_route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)
    current_route_sequence = Column(Integer, nullable=True)
    current_route_progress_km = Column(Float, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    id = Column(Integer, primary_key=True, index=True)
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=True)
    risk_score = Column(Float)
    risk_level = Column(String)
    factors = Column(Text, nullable=True)
    predicted_at = Column(DateTime, server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String)  # blocked_road / high_risk / delay / weather / bridge_condition
    message_en = Column(Text)
    message_local = Column(Text, nullable=True)
    language = Column(String, default="en")
    road_id = Column(Integer, ForeignKey("roads.id"), nullable=True)
    bridge_id = Column(Integer, ForeignKey("bridges.id"), nullable=True, index=True)
    severity = Column(String, default="medium")
    status = Column(String, default="active", index=True)
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime, nullable=True)
