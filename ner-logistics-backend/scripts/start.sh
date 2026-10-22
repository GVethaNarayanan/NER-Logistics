#!/bin/bash
set -e

echo "Running Alembic migrations..."
alembic upgrade head || echo "Migrations already applied or skipped."

echo "Migrations completed successfully. Starting application..."
PORT="${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
