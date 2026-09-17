"""
Application configuration — loaded from environment variables and .env file.

Pydantic Settings resolution order:
  1. Init keyword arguments
  2. Environment variables
  3. .env file
  4. Field defaults (below)

Do NOT wrap defaults in os.getenv() — that bypasses Pydantic's .env loading.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra env vars in .env without raising errors
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    # No Postgres running yet? No problem — SQLite is the default so you can
    # start building today. Swap in your real DATABASE_URL when you deploy.
    database_url: str = "sqlite:///./ner_logistics.db"

    # ── Open-Meteo (free weather API, no key required) ────────────────────
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"

    # ── CORS ──────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, or "*" for all (dev only).
    cors_origins: str = "*"

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Application metadata ──────────────────────────────────────────────
    app_name: str = "SIH26002 - NER Smart Logistics & Accessibility Intelligence Platform"

    # ── JWT Authentication ────────────────────────────────────────────────
    # CRITICAL: Override jwt_secret_key in production via JWT_SECRET_KEY env var.
    # The default below is for local development ONLY.
    jwt_secret_key: str = "DEV-ONLY-CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 1440  # 24 hours

    # ── Seed admin (development / first-run bootstrapping) ────────────────
    # These are read from env vars so production credentials are never in code.
    seed_admin_username: str = "admin"
    seed_admin_password: str = "admin_dev_password"
    seed_admin_email: str = "admin@ner-logistics.dev"

    # ── Vehicle Simulation ────────────────────────────────────────────────
    # Set to false via VEHICLE_SIMULATION_ENABLED=false to disable the
    # background vehicle movement simulator (e.g. in production or testing).
    vehicle_simulation_enabled: bool = True


settings = Settings()
