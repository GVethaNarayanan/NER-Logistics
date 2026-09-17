# SIH26002 — Implementation Log

This log records what was built, key decisions, limitations, and data source
classifications for each implementation phase.

---

## Phase 1 — Architecture Foundation (2026-09-07)

### Changes Made

| File | Change | Reason |
|---|---|---|
| `app/config.py` | Rewrote using Pydantic Settings v2 API (`SettingsConfigDict`), removed `os.getenv()` wrapping, added `cors_origins`, `log_level`, `app_name` fields | Old implementation bypassed `.env` file loading because `os.getenv()` was evaluated at class definition time, before Pydantic loaded the `.env` file. New fields support the CORS, logging, and metadata features added in this phase. |
| `app/main.py` | Added CORS middleware, structured logging (stdout), three global exception handlers (HTTP, validation, unhandled), enriched FastAPI metadata | Frontend needs CORS; structured logging provides observability; consistent error response shape (`{"error": {"code", "message", "detail", "path"}}`) gives the frontend a single contract for error handling. |
| `.env.example` | Documented all new configuration fields | Developer experience — new contributors can see all available settings. |

### Design Decisions

1. **Error response shape**: All errors now return
   `{ "error": { "code": <int>, "message": <str>, "detail": <any|null>, "path": <str> } }`.
   This is the contract the React frontend will rely on for error handling.

2. **CORS origins**: Defaults to `"*"` for local development. Production should
   restrict to the deployed frontend domain via the `CORS_ORIGINS` env var.

3. **Logging format**: `timestamp | LEVEL    | logger_name          | message` —
   structured enough for grep/search, human-readable for development.
   Level is configurable via `LOG_LEVEL` env var.

4. **Config fix**: Switched from `os.getenv()` defaults (which bypass `.env` file)
   to plain default values with Pydantic Settings v2 `SettingsConfigDict`. This
   restores the intended resolution order: env vars → .env file → defaults.

### Preserved Functionality

- All 7 existing routers remain registered and untouched
- Health check endpoint preserved (now also returns `version`)
- SQLite/Postgres switching via `DATABASE_URL` still works
- `Base.metadata.create_all()` still runs at startup

### Limitations

- No rate limiting (deferred to Phase 12)
- CORS set to `*` by default — must be restricted for production

---

## Phase 3 — Authentication & Authorization (2026-09-07)

### Architecture

```
Client → POST /auth/login (OAuth2 form) → JWT access + refresh tokens
       → Authorization: Bearer <access_token> → protected endpoints
       → POST /auth/refresh (refresh_token) → new token pair
```

**Password hashing**: bcrypt (direct, not via passlib — see compatibility note below)
**Token format**: JWT (HS256) via python-jose
**Access tokens**: 30 min default, configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`
**Refresh tokens**: 24 h default, configurable via `REFRESH_TOKEN_EXPIRE_MINUTES`

### Changes Made

| File | Change | Reason |
|---|---|---|
| `app/config.py` | Added JWT settings (`jwt_secret_key`, `jwt_algorithm`, `access_token_expire_minutes`, `refresh_token_expire_minutes`) and seed admin credentials | All secrets configurable via env vars, not hardcoded |
| `app/models.py` | Added `User` model with `username`, `email`, `hashed_password`, `role`, `is_active`, `created_at`. Added `VALID_ROLES` constant. Added `Boolean` import | Authentication requires a user table |
| `app/schemas.py` | Added `UserRegister` (with validators), `UserOut`, `UserLogin`, `TokenResponse`, `TokenRefreshRequest` schemas | Pydantic validation for auth endpoints. `UserOut` never exposes `hashed_password` |
| `app/services/auth_service.py` | **[NEW]** Password hashing (bcrypt direct), JWT creation/validation, user CRUD helpers, timing-safe `authenticate_user` | Centralized auth logic, no timing attacks on login |
| `app/dependencies.py` | **[NEW]** `get_current_user` (JWT validation), `require_role(*roles)` factory, `OAuth2PasswordBearer` | Reusable auth dependencies for any router |
| `app/routers/auth.py` | **[NEW]** `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` | Auth endpoints with OAuth2-compatible login for Swagger |
| `app/routers/bridges.py` | Added `require_role` to `POST /` (admin) and `PATCH /{id}/condition` (field_official, admin) | Write protection |
| `app/routers/incidents.py` | Added `require_role` to `POST /` (field_official, admin) | Write protection |
| `app/routers/vehicles.py` | Added `require_role` to `POST /` (admin) and `PATCH /{id}/location` (field_official, admin) | Write protection |
| `app/routers/alerts.py` | Added `require_role` to `POST /` (admin) | Write protection |
| `app/main.py` | Registered `auth.router` | Enable auth endpoints |
| `scripts/seed_admin.py` | **[NEW]** Idempotent admin seed script, reads creds from env vars | Development bootstrap without hardcoded production passwords |
| `tests/conftest.py` | **[NEW]** In-memory SQLite fixtures, user factories, login helper | Isolated test environment |
| `tests/test_auth.py` | **[NEW]** 35 tests covering all auth scenarios | Comprehensive verification |
| `tests/verify_swagger.py` | **[NEW]** End-to-end flow verification against running server | Swagger/integration verification |
| `requirements.txt` | Added `python-jose[cryptography]`, `passlib[bcrypt]`, `bcrypt`, `python-multipart`, `pytest`, `httpx` | Auth and test dependencies |
| `.env.example` | Added JWT and seed admin configuration docs | Developer onboarding |

### Roles & Permissions

| Role | Can do |
|---|---|
| `field_official` | Create incidents, update bridge conditions, update vehicle locations |
| `admin` | Everything field_official can + create bridges, create vehicles, create alerts |

### Public vs. Protected Endpoints

| Endpoint | Auth | Reason |
|---|---|---|
| `GET /roads/`, `GET /roads/{id}` | Public | GIS dashboard read access |
| `GET /bridges/` | Public | GIS dashboard read access |
| `GET /incidents/` | Public | GIS dashboard read access |
| `GET /vehicles/` | Public | GIS dashboard read access |
| `GET /alerts/` | Public | GIS dashboard read access |
| `GET /weather/*` | Public | GIS dashboard read access |
| `POST /risk/predict` | Public | GIS dashboard risk assessment |
| `GET /` | Public | Health check |
| `POST /auth/register` | Public | Self-registration |
| `POST /auth/login` | Public | Login |
| `POST /auth/refresh` | Public | Token refresh |
| `GET /auth/me` | **JWT** | User profile |
| `POST /incidents/` | **field_official / admin** | Field data entry |
| `PATCH /bridges/{id}/condition` | **field_official / admin** | Field data entry |
| `PATCH /vehicles/{id}/location` | **field_official / admin** | GPS updates |
| `POST /bridges/` | **admin** | Infrastructure management |
| `POST /vehicles/` | **admin** | Fleet management |
| `POST /alerts/` | **admin** | Alert management |

### Security Decisions

1. **bcrypt direct instead of passlib**: passlib 1.7.x is incompatible with bcrypt >= 4.1
   on Python 3.13 (`__about__` attribute removed). Using `bcrypt.hashpw()`/`bcrypt.checkpw()`
   directly provides the same security without the broken wrapper.

2. **Timing-safe authentication**: `authenticate_user` hashes a dummy password when the
   username doesn't exist, preventing timing attacks that could enumerate valid usernames.

3. **No credential revelation**: Invalid login returns "Invalid credentials" — never says
   whether the username or password was specifically wrong.

4. **Privilege escalation prevention**: `UserRegister` schema validates that `role` must be
   `"field_official"`. Admin accounts can only be created via the seed script or by another
   admin (future admin management endpoint).

5. **Token type enforcement**: Refresh tokens cannot be used as access tokens (and vice versa)
   because the `type` claim is validated in `get_current_user` and `/auth/refresh`.

6. **No secrets in source code**: JWT secret key has a dev-only default; production
   **must** override via `JWT_SECRET_KEY` env var.

### Seed Admin Process

```bash
# Default dev credentials (override via env vars for production):
python scripts/seed_admin.py

# Custom credentials:
SEED_ADMIN_USERNAME=myadmin SEED_ADMIN_PASSWORD=strongpass SEED_ADMIN_EMAIL=admin@example.com python scripts/seed_admin.py
```

Idempotent — running multiple times will not create duplicate accounts.

### Test Results (35/35 passed)

| Category | Tests | Result |
|---|---|---|
| Registration | 6 (success, duplicate username, duplicate email, admin role rejection, short password, short username) | All passed |
| Login | 3 (success, wrong password, nonexistent user) | All passed |
| Token validation | 4 (valid token, no token, invalid token, malformed header) | All passed |
| Refresh tokens | 3 (success, invalid token, access-token-as-refresh rejected) | All passed |
| Protected without auth | 4 (incident, bridge condition, alert, vehicle location — all 401) | All passed |
| Protected with auth | 3 (field_official incident, admin alert, admin bridge) | All passed |
| Role restrictions | 4 (field_official blocked from admin-only, field_official allowed for field-level, admin has full access) | All passed |
| Public endpoints | 8 (roads, roads/{id}, bridges, incidents, vehicles, alerts, risk, health) | All passed |

### Known Limitations

- JWT secret uses a dev-only default — **must** be overridden in production
- No token blacklist/revocation (refresh tokens remain valid until expiry)
- No admin user management endpoint (only seed script for now)
- passlib remains in requirements.txt as a transitive dependency but is not used directly
- `GET /roads/{id}` returns 500 when ID doesn't exist (pre-existing router bug, Phase 4 fix)

---

## Phase 4 — Core Infrastructure APIs (2026-09-07)

### Changes Made

| File | Change | Reason |
|---|---|---|
| `app/schemas.py` | Added generic `PaginatedResponse`, `DistrictConnectivity`, `RoadCounts`, `BridgeCounts` | Standardize pagination across all list endpoints and support the district connectivity API |
| `app/routers/roads.py` | Rewrote to use pagination, filtering by `district` and `status` (case-insensitive DB queries), deterministic sort, fixed 404 handling | Meet Phase 4 road filtering and pagination requirements |
| `app/routers/bridges.py` | Rewrote to use pagination, filtering by `road_id` and `condition`, FK validation on `POST`, fixed 404, auto-update `last_verified` | Meet Phase 4 bridge API requirements and maintain data integrity |
| `app/routers/incidents.py` | Added pagination and filtering to list endpoint | Phase 4 requirement |
| `app/routers/vehicles.py` | Added pagination and filtering to list endpoint, fixed 404 on PATCH | Phase 4 requirement |
| `app/routers/alerts.py` | Added pagination and filtering to list endpoint | Phase 4 requirement |
| `app/routers/districts.py` | **[NEW]** Created `GET /districts/{district}/connectivity` | Computed connectivity from real DB data via SQL aggregation (no hardcoding) |
| `app/main.py` | Registered `districts` router | Enable new endpoint |
| `tests/test_phase4.py` | **[NEW]** 47 unit/integration tests for Phase 4 | Ensure correctness of pagination, filtering, 404s, and auth regression |
| `tests/test_auth.py` | Updated tests to match Phase 4 changes (201 status for bridge POST, proper 404 for roads/{id}) | Prevent tests from failing due to bug fixes |
| `tests/verify_phase4.py` | **[NEW]** End-to-end integration test against a live server | Final verification that all endpoints work, filter, paginate, and are protected properly |

### Key Improvements

1. **Global Pagination**: Introduced a standardized `{"items", "total", "skip", "limit"}` structure across all five core endpoints (`roads`, `bridges`, `incidents`, `vehicles`, `alerts`).
2. **True Aggregation**: District connectivity performs direct SQL aggregations on `roads` and `bridges` (joined) rather than loading everything into Python or using fake data.
3. **FK Validation**: When creating a bridge, it now queries the DB to ensure the `road_id` actually exists, returning a clear 404 otherwise.
4. **Resilience**: Cleaned up pre-existing bugs (e.g. `roads/{id}` returning `None` and causing 500s).
5. **Auth Preserved**: Comprehensive regression testing confirmed that the Phase 3 `require_role` system remains intact and public read access is unbroken.

### Test Results

- All 35 Phase 3 tests passed.
- All 47 Phase 4 tests passed.
- End-to-end swagger integration script verified successful API interactions against a live server.

---

## Phase 5: Weather Integration into the Risk Pipeline

**Status:** Completed  
**Goal:** Integrate the Open-Meteo weather client into the backend risk pipeline using a periodic background job, and extend the `/risk/predict` endpoint to automatically pull in real-time or fallback weather and infrastructure data based on a provided `road_id`.

### Files Modified

| File | Change | Reason |
|---|---|---|
| `requirements.txt` | Added `apscheduler` and `alembic` | Needed for periodic background job and DB migrations |
| `app/models.py` | Added `data_source` column to `WeatherSnapshot` with default `"verified"` | To clearly track provenance of fetched weather data |
| `alembic/env.py` | Initialized Alembic and configured `target_metadata` and DB URL | To support "proper reversible Alembic migration" and capture existing schema |
| `alembic/versions/*` | **[NEW]** Created initial and `data_source` migrations | DB schema evolution without losing data |
| `app/services/weather_job.py` | **[NEW]** Created background scheduler job `fetch_and_store_weather` | Periodically fetches Open-Meteo data for unique Road start locations and persists to DB |
| `app/main.py` | Added `@asynccontextmanager` `lifespan` event | Start scheduler on app startup, clean shutdown on exit |
| `app/routers/risk.py` | Extended `/risk/predict` to handle `road_id` | Automatic mode: pulls Road condition, Bridge condition, and nearest WeatherSnapshot |
| `tests/test_phase5.py` | **[NEW]** Added tests for scheduler, fetch success/failure, auto risk (fresh & stale), and manual mode | Ensure 100% adherence to Phase 5 requirements |

### Key Improvements

1. **Weather Scheduler Architecture**: Built using `APScheduler.BackgroundScheduler`. Scheduled to run every 60 minutes. Fetches weather per distinct Road start location (`lat`, `lon`), preventing unnecessary duplicate API calls.
2. **Robust API Failure Handling**: The `fetch_and_store_weather` job wraps the Open-Meteo call in `try/except`. If the external API times out or fails, it gracefully logs the failure and continues without crashing the application.
3. **Data Source Identification**: The newly created Alembic migration added a `data_source` column to `WeatherSnapshot`. The job saves it precisely as `"verified"`.
4. **Location Matching**: Automatic risk prediction matches a `WeatherSnapshot` against a Road's `start_lat`/`start_lon` within a strict `0.1` degree geographic tolerance (~10km) using SQL `between()`.
5. **Fresh vs Stale Fallback**: Fallback threshold is set to `6 hours`. If a weather snapshot is older than 6 hours, it is flagged as stale. The response includes `"Weather data: stale/fallback"` in the factors list.
6. **No-Data Behavior**: If no matching verified snapshot is found within the tolerance, it raises an HTTP 400 (`"No verified weather data available for this location"`) rather than fabricating data.
7. **Manual Backward Compatibility**: Supplying explicit rainfall/condition parameters without `road_id` correctly calculates the risk score as it always did.

### Test Results
- **Phase 5 Specific**: 7 specific Phase 5 tests passed covering fetching, API failure handling, auto risk prediction (fresh, stale, no-data), manual risk prediction, and scheduler lifecycle.
- **Regressions**: All 82 previously defined Phase 1-4 tests passed. No authentication or endpoints were broken.
- **Total test results**: 89 passed.

### Known Limitations
- The weather matching currently strictly requires the snapshot to be within 0.1 degrees of the Road's `start_lat`/`start_lon`. If district centers are used instead, we would need to slightly increase the tolerance or match by District Name mapping.
- `Alembic` was initialized during this phase. Developers checking out the project freshly must now apply `alembic upgrade head`.

---

## Phase 6: Incident / Field Reporting Completion

**Status:** Completed  
**Goal:** Finalize the incident reporting module by implementing geo-tag validation, advanced incident filtering, lifecycle management (`status` tracking), real media uploads, and offline batch synchronization.

### Files Modified

| File | Change | Reason |
|---|---|---|
| `app/models.py` | Added `status` column to `Incident` with default `"reported"` | To track the lifecycle (`reported` -> `verified` -> `resolved`) |
| `alembic/versions/*` | **[NEW]** Created `add_status_to_incidents` migration | Safely inject the `status` column into the DB without data loss |
| `app/schemas.py` | Overhauled `Incident` schemas | Geo validation (-90/90, -180/180), enforced server-side default status, added batch response schemas |
| `app/routers/incidents.py` | Complete endpoint enhancements | `GET` with multi-filter (date, status, road, bridge). `POST /sync-batch` for offline queues. `PATCH /{id}/status` for lifecycle handling. `POST /{id}/photo` for real multipart local file uploads |
| `app/main.py` | Mounted `./media` via `StaticFiles` | Serve development photo uploads |
| `LIMITATIONS.md` | **[NEW]** Created limitation docs | Documented dev-only status of local `/media` storage and batch sync idiosyncrasies |
| `tests/test_phase6.py` | **[NEW]** 8 Phase 6 tests | Guaranteed behavior for lifecycles, filters, sync batching, photo uploads, and geo-validation |

### Key Improvements

1. **Incident Status Lifecycle**: Introduced rigorous backend rules that force newly submitted incidents to `status="reported"`. Users cannot bypass this. Only authorized `field_official` or `admin` users can transition it to `verified` and `resolved` strictly sequentially. Nonsensical backwards transitions (e.g., `resolved` to `reported`) throw HTTP 400 validation errors.
2. **Offline Batch Syncing with Partial Success**: The `POST /sync-batch` endpoint takes an array of incidents. It validates each one individually against the Database (verifying FK existence like `road_id`). Valid records are persisted and given `synced="synced"`. Invalid records are skipped. The endpoint responds with `successful_ids` and `failed_indexes`, allowing the frontend to know precisely which incidents in their offline queue to flush or retry.
3. **Geo-Location Fencing**: Rigorous `Pydantic` `Field` limits force latitudes to `-90`..`90` and longitudes to `-180`..`180`. Any arbitrary or fabricated coordinate range will 422 fail.
4. **Real Multipart Photo Upload**: `POST /{id}/photo` actually stores image files (`.jpg`, `.png`, etc.) to the local disk `./media/`. It verifies the file is an image, restricts sizes, and generates a safe unique UUID-driven filename, preventing any path traversal vulnerabilities.
5. **Dynamic Incident Filtering**: `GET /incidents` allows combinable `road_id`, `bridge_id`, `status`, `start_date`, `end_date`, `incident_type`, and `severity` query parameters powered entirely by SQLAlchemy for optimal SQL execution.

### Test Results
- **Phase 6 Specific**: 8 specific Phase 6 tests passed (testing everything from coordinate rejection, batch auth, to manual status transitions and file uploads).
- **Regressions**: All 89 previously defined Phase 1-5 tests passed.
- **Total test results**: 97 passed.

### Known Limitations
- Defined extensively in `LIMITATIONS.md`, but crucially: Local `./media` storage is purely for development environments. Production must be migrated to S3. Offline batch syncing lacks a client-generated UUID idempotency key to prevent identical duplicate submissions if network faults prompt multiple retries.

---

## Phase 9: Risk-Aware Routing and Alternative Path Intelligence

**Status:** Completed  
**Goal:** Implement Risk-Aware Routing ("safest" vs "shortest" preference) into the existing GIS/routing foundation, incorporating verified weather, unresolved incidents, and bridge conditions to calculate a risk_cost penalty.

### Files Modified

| File | Change | Reason |
|---|---|---|
| `app/schemas.py` | Added `preference` field (`Literal["shortest", "safest"]`) to `RouteRequest`. Expanded `RouteResponse` properties with risk metrics. | Expose routing options to clients. |
| `app/services/graph_service.py` | Centralized dynamic `risk_cost` calculation based on bulk DB queries (roads, recent verified weather, unresolved incidents, bridges). | Eliminated N+1 queries during graph construction; mapped risk factors to edges. |
| `app/services/routing_service.py` | Updated `_add_virtual_node` and `find_route` to support both `distance_km` and `risk_cost` weights. Extracts risk metadata (`average_risk_score`, `max_risk_score`, `risk_level`) into GeoJSON. | Core pathfinding logic enhanced for "safest" preference and proportional splitting. |
| `app/routers/routing.py` | Passed `preference` down from `RouteRequest` to `find_route`. | Complete the API contract for route calculation. |
| `tests/test_phase9.py` | **[NEW]** Comprehensive test suite for Phase 9 features. | Guaranteed safest/shortest divergence, multiple hazards, stale weather ignoring, and same-edge proportional splitting. |

### Key Improvements

1. **Deterministic Risk Cost**: Designed a formula `risk_cost = distance_km * (1.0 + (risk_score / 100.0) * 9.0)` which heavily penalizes risky edges up to 10x without breaking the graph topology.
2. **Bulk Bounded Queries**: The `graph_service` calculates risk factors using exactly 4 bulk database queries rather than an O(N) loop of N+1 database queries, ensuring routing remains highly performant for thousands of roads.
3. **Advanced Safest Routing**: If `safest` is requested, the system automatically prefers longer detours if the direct route has verified incidents, poor bridge conditions, or heavy verified rainfall.
4. **Intelligent Staleness Awareness**: Uses Phase 5 rules: weather data older than 6 hours is automatically bypassed. Unverified incidents or resolved incidents are excluded from risk calculations.
5. **GeoJSON Risk Metadata**: The response now intelligently computes `average_risk_score`, `max_risk_score`, and maps it to a `risk_level` (LOW, MEDIUM, HIGH) which the frontend can use for color-coding.

### Test Results
- **Phase 9 Specific**: 10 tests passed covering all advanced routing scenarios (divergence, default preferences, virtual-node splitting, and performance/bulk query checking).
- **Regressions**: All 170 previously defined tests across auth, GIS, weather, incidents, and Phase 8 routing passed successfully.
- **Total test results**: 180 passed.

### Known Limitations
- NetworkX `shortest_path` does not easily support multi-objective optimization (e.g., "safest path that is no more than 20% longer"). This is a Phase 10 Tier 2 feature if desired, currently it purely minimizes `risk_cost`.

---

## Phase 12: Backend Hardening, Docker & Verification

**Status:** Completed  
**Goal:** Make the existing backend genuinely runnable, testable, documented, containerized, and ready for a frontend.

### Files Modified

| File | Change | Reason |
|---|---|---|
| `requirements.txt` | Added `psycopg2-binary` | Required for PostgreSQL deployment. |
| `.env.example` | Added `VEHICLE_SIMULATION_ENABLED` | Documented background job toggle. |
| `Dockerfile` | **[NEW]** Created `python:3.13-slim` image | Production container with non-root `appuser`. |
| `docker-compose.yml` | **[NEW]** Created stack with API + PostgreSQL | Isolated database environment for deployment. |
| `scripts/start.sh` | **[NEW]** Added Alembic upgrade script | Auto-runs `alembic upgrade head` before Uvicorn starts. |
| `scripts/verify_openapi.py` | **[NEW]** OpenAPI schema verification | Validates all routers are registered and schemas match implementation. |

### Key Improvements

1. **Dockerized Environment**: The API is now deployable via `docker compose up -d` with a fully isolated PostgreSQL container and persistent volumes.
2. **Auto-migrations**: Container startup guarantees `alembic upgrade head` runs before accepting API traffic, failing fast if the DB is incompatible.
3. **OpenAPI Verification**: A dedicated script verified that 100% of the Phase 1-11 implemented endpoints are present in the Swagger spec with correct request/response shapes.
4. **Comprehensive Test Baseline**: The test suite covers `auth`, `roads`, `bridges`, `weather`, `incidents`, `vehicles`, `risk`, `alerts`, `districts`, `routes`, and `routing` with an unbroken 228/228 pass rate. No existing logic was broken or fabricated.

### Test Results
- **Final Test Count**: 228 passing tests.
- **Failures**: 0.
- **Regressions**: 0.

### Known Limitations
- **Docker Testing**: Full Docker runtime testing could not be completed on the development machine due to Docker daemon unavailability. This is explicitly noted in `LIMITATIONS.md`.
