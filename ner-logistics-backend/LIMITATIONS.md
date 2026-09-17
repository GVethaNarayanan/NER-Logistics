# Backend Limitations

## 1. Photo Upload Storage
**Local filesystem storage (`/media`) is strictly for development.** 
Currently, the `POST /incidents/{id}/photo` endpoint saves files to the local disk and serves them using FastAPI's `StaticFiles`. 
**For Production**, this MUST be refactored to use a secure S3-compatible cloud object storage (e.g. AWS S3, MinIO) to prevent server disk exhaustion, allow horizontal scaling, and ensure durable backup.

## 2. Offline Batch Sync Idempotency
The `POST /incidents/sync-batch` endpoint currently lacks true idempotency based on client-generated UUIDs. Exact duplicate offline submissions sent multiple times due to patchy networks might be recorded multiple times if they are fundamentally valid. To solve this in production, a client-generated UUID field (e.g., `client_id`) should be added to the model and enforced with a unique constraint.

## 3. Weather Geographic Tolerance
The Phase 5 automatic risk prediction matches weather snapshots against roads using a strict `0.1`-degree tolerance (~10km). If a snapshot falls slightly outside this bounding box, the endpoint will return an error stating no verified weather data is available rather than using a distant snapshot. This is intentionally restrictive to prevent fabricating data.

## 4. Environment Verification (Phase 12)
While `Dockerfile` and `docker-compose.yml` are provided for containerized deployment, full local runtime verification inside Docker could not be performed due to Docker daemon unavailability in the current test environment. As such, local database (`sqlite:///./ner_logistics.db`) was heavily tested while the PostgreSQL integration via Docker Compose must be verified manually on a Docker-capable host.
