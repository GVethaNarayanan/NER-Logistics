#!/bin/bash
set -e

echo "Starting application on port ${PORT:-8000}..."
PORT="${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
