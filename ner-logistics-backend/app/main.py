"""
SIH26002 — NER Smart Logistics & Accessibility Intelligence Platform

FastAPI application entry point.
- CORS middleware for cross-origin frontend access
- Structured logging (stdout, configurable level)
- Global exception handlers for consistent error responses
- All domain routers mounted under their respective prefixes
"""
import logging
import sys

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import Base, engine
from app.routers import roads, bridges, weather, incidents, vehicles, risk, alerts, auth, districts
from app.services.weather_job import start_scheduler, shutdown_scheduler

# ── Structured logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("ner_logistics")

# ── Database bootstrap (replaced by Alembic migrations in Phase 3) ────────────
Base.metadata.create_all(bind=engine)
from app.services.ml_service import ml_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load Tier 2 ML Model (skip during pytest to preserve legacy test determinism)
    import sys
    if "pytest" not in sys.modules:
        ml_service.load_model()
    # Start the vehicle GPS simulation background task
    start_scheduler()
    yield
    # Shutdown
    shutdown_scheduler()

import os
from fastapi.staticfiles import StaticFiles

# ── FastAPI application ───────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Backend API for the AI-Based Smart Logistics & Accessibility "
        "Intelligence Platform for the North Eastern Region (SIH26002)."
    ),
    lifespan=lifespan,
)

# Ensure media directory exists for Phase 6
os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# ── CORS middleware ───────────────────────────────────────────────────────────
_cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS enabled for origins: %s", _cors_origins)


# ── Global exception handlers ─────────────────────────────────────────────────
# Every error response follows the shape:
#   { "error": { "code": <int>, "message": <str>, "detail": <any|null>, "path": <str> } }
# This gives the frontend a single, predictable contract for error handling.

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle FastAPI/Starlette HTTP exceptions (404, 403, 401, etc.)."""
    logger.warning(
        "HTTP %d | %s %s | %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": str(exc.detail),
                "detail": None,
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """Handle Pydantic validation errors on request bodies/params."""
    errors = exc.errors()
    logger.warning(
        "Validation error | %s %s | %d issue(s)",
        request.method,
        request.url.path,
        len(errors),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Request validation failed",
                "detail": [
                    {
                        "field": " -> ".join(str(loc) for loc in e.get("loc", [])),
                        "message": e.get("msg", ""),
                        "type": e.get("type", ""),
                    }
                    for e in errors
                ],
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — log full traceback, return safe 500."""
    logger.error(
        "Unhandled exception | %s %s | %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "detail": None,
                "path": request.url.path,
            }
        },
    )


from app.routers import roads, bridges, weather, incidents, vehicles, risk, alerts, auth, districts, routes, routing

# ── Router registration ──────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(roads.router)
app.include_router(bridges.router)
app.include_router(weather.router)
app.include_router(incidents.router)
app.include_router(vehicles.router)
app.include_router(risk.router)
app.include_router(alerts.router)
app.include_router(districts.router)
app.include_router(routes.router)
app.include_router(routing.router)

logger.info("Application started: %s (v0.1.0)", settings.app_name)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["health"])
def health_check():
    """Simple liveness probe — returns 200 if the service is running."""
    return {"status": "ok", "service": settings.app_name, "version": "0.1.0"}
