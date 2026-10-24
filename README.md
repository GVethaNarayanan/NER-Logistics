# 🚛 NER Logistics — AI-Based Smart Logistics & Accessibility Intelligence Platform

> **SIH26002** | An AI-powered logistics intelligence platform for North Eastern Region (NER) of India

[![Live Demo](https://img.shields.io/badge/🌐_Live_Demo-Vercel-000?style=for-the-badge)](https://ner-logistics-vetha-narayanan-g.vercel.app)
[![API Docs](https://img.shields.io/badge/📡_API_Docs-Swagger-85EA2D?style=for-the-badge)](https://ner-logistics-1.onrender.com/docs)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=white)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostGIS-15-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgis.net)

---

## 📋 Project Objective

To develop an AI-powered logistics intelligence platform that improves **transportation accessibility and decision-making** across the North Eastern Region by:

- Monitoring road & bridge infrastructure in real-time
- Predicting disruption risks using ML models
- Recommending optimal and safest routes
- Providing timely alerts for weather, incidents, and infrastructure damage

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (React + Vite)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │Dashboard │ │Incidents │ │ Vehicles │ │  Alerts  │          │
│  │  (GIS)   │ │Reporting │ │ Tracking │ │  Panel   │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
│       └─────────────┴────────────┴─────────────┘               │
│                         REST API                                │
├─────────────────────────────────────────────────────────────────┤
│                   BACKEND (FastAPI + Python)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Routing  │ │   Risk   │ │ Weather  │ │  Alert   │          │
│  │ Engine   │ │  Engine  │ │  Client  │ │   Job    │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
│       │             │            │             │                │
│  ┌────┴─────┐ ┌─────┴────┐ ┌────┴─────┐ ┌────┴─────┐         │
│  │ NetworkX │ │ ML Model │ │ Open-    │ │ Cron     │          │
│  │ DiGraph  │ │(Gradient │ │ Meteo API│ │ Scheduler│          │
│  │ + PostGIS│ │ Boosting)│ │          │ │          │          │
│  └────┬─────┘ └──────────┘ └──────────┘ └──────────┘          │
├───────┴─────────────────────────────────────────────────────────┤
│              DATABASE (PostgreSQL + PostGIS)                     │
│  Roads (227K) │ Bridges │ Incidents │ Weather │ Vehicles       │
│  Districts    │ Routes  │ Alerts    │ Users   │ Sessions       │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

### 🗺️ GIS Dashboard & Route Planning
- **Interactive Leaflet map** with real-time road network visualization
- **227,000+ OSM roads** across all 8 NER states loaded via PostGIS
- **Shortest & Safest route** computation using Dijkstra's algorithm on NetworkX DiGraph
- **Progressive road display** — zoom-level-aware rendering for optimal performance
- **Island stitching algorithm** — auto-bridges disconnected OSM components for 100% route success

### 🔍 AI/ML Risk Prediction
- **Gradient Boosting model** trained on rainfall, road condition, bridge health, terrain, and incident data
- **Tier 1 heuristic engine** with weighted multi-factor risk scoring
- **Real-time risk levels**: LOW / MEDIUM / HIGH with color-coded visualization
- **Per-route risk assessment** with deferred batch computation for performance

### 🌦️ Weather Intelligence
- **Open-Meteo API integration** for live rainfall and forecast data
- **Geometry-based weather matching** — maps weather stations to road corridors via PostGIS spatial queries
- **Uncertainty penalty** — missing weather data is treated as moderate risk, not safe

### 🚗 Vehicle & Fleet Tracking
- **Simulated GPS tracking** with realistic NER coordinate movement
- **Live vehicle markers** on the GIS dashboard
- **Vehicle registration** with type, capacity, and district assignment

### 🚨 Incident Management
- **Field reporting** with incident type, severity, location, and photo upload
- **Lifecycle management**: Reported → Verified → Resolved
- **Auto road status update**: Damaging incidents (landslide/flood/road_damage) automatically set roads to `blocked` or `restricted`
- **Auto road restoration**: When incidents are resolved, road status reverts to `open`
- **Routing graph cache invalidation** on every status change for immediate route updates

### 🌉 Bridge Monitoring
- **Bridge condition tracking**: Good / Fair / Poor / Critical
- **Hazard cause analysis**: Landslide, flood, structural, erosion — with detailed descriptions
- **Route-aware bridge display**: Bridges on computed routes are highlighted with risk indicators

### 🔔 Automated Alert System
- **Background alert job** scans for high-risk conditions (weather, incidents, bridge damage)
- **Alert lifecycle**: Active → Acknowledged → Resolved
- **District-level alerts** with severity classification

### 📋 Saved Routes
- **Admin creates** pre-planned supply corridors
- **All users can view** saved routes with live road status
- **Real-time route health**: Shows blocked/restricted segments based on current conditions

### 🔐 Authentication & Authorization
- **JWT-based authentication** with role-based access control
- **Roles**: Admin, Field Official
- **Registration & login** with secure password hashing (bcrypt)

### 🌐 Internationalization
- **Multi-language support**: English + Assamese (অসমীয়া)
- **i18next integration** with language switcher in the navbar

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, TypeScript, Vite, Leaflet, Tailwind CSS, Lucide Icons |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy, Alembic, NetworkX |
| **Database** | PostgreSQL 15 + PostGIS (Supabase hosted) |
| **ML/AI** | Scikit-learn (Gradient Boosting), NumPy |
| **Maps** | OpenStreetMap data, Leaflet.js, PostGIS spatial queries |
| **Weather** | Open-Meteo API (real-time + forecast) |
| **Auth** | JWT (PyJWT), bcrypt password hashing |
| **Deployment** | Vercel (frontend), Render (backend) |
| **VCS** | Git + GitHub |

---

## 📁 Project Structure

```
NER-Logistics/
├── ner-logistics-frontend/          # React + Vite frontend
│   ├── src/
│   │   ├── api/                     # API client modules
│   │   ├── components/              # Reusable UI components
│   │   │   ├── dashboard/           # Map, NavigationHUD, RiskPanel
│   │   │   └── shared/              # ErrorState, LoadingSpinner
│   │   ├── contexts/                # AuthContext (JWT state)
│   │   ├── i18n/                    # Internationalization (EN/AS)
│   │   ├── pages/                   # Route pages
│   │   │   ├── Home.tsx             # GIS Dashboard + Route Planner
│   │   │   ├── Incidents.tsx        # Incident reporting & list
│   │   │   ├── Vehicles.tsx         # Fleet management
│   │   │   ├── Alerts.tsx           # Alert monitoring
│   │   │   ├── SavedRoutes.tsx      # Saved route corridors
│   │   │   ├── Login.tsx            # Authentication
│   │   │   └── Register.tsx         # User registration
│   │   └── App.tsx                  # Router & layout
│   └── package.json
│
├── ner-logistics-backend/           # FastAPI backend
│   ├── app/
│   │   ├── routers/                 # API endpoints
│   │   │   ├── auth.py              # Login, register, JWT
│   │   │   ├── roads.py             # Road CRUD + viewport bbox
│   │   │   ├── bridges.py           # Bridge monitoring
│   │   │   ├── incidents.py         # Incident lifecycle
│   │   │   ├── vehicles.py          # Fleet tracking
│   │   │   ├── routing.py           # Route computation API
│   │   │   ├── routes.py            # Saved route management
│   │   │   ├── risk.py              # Risk prediction API
│   │   │   ├── alerts.py            # Alert management
│   │   │   ├── districts.py         # District registry
│   │   │   └── weather.py           # Weather data
│   │   ├── services/                # Business logic
│   │   │   ├── graph_service.py     # OSM road graph builder (vertex-sharing topology)
│   │   │   ├── routing_service.py   # Dijkstra routing + 3-layer fallback
│   │   │   ├── risk_engine.py       # Multi-factor risk scoring
│   │   │   ├── ml_service.py        # Gradient Boosting ML model
│   │   │   ├── weather_client.py    # Open-Meteo API client
│   │   │   ├── weather_match.py     # Geometry-based weather matching
│   │   │   ├── weather_job.py       # Background weather fetcher
│   │   │   ├── alert_job.py         # Automated alert scanner
│   │   │   ├── simulation_job.py    # GPS simulation engine
│   │   │   ├── vehicle_service.py   # Vehicle logic + haversine
│   │   │   └── auth_service.py      # JWT + password hashing
│   │   ├── models.py                # SQLAlchemy ORM models
│   │   ├── schemas.py               # Pydantic request/response schemas
│   │   ├── database.py              # DB connection + session
│   │   └── main.py                  # FastAPI app + CORS + startup
│   ├── alembic/                     # Database migrations
│   ├── tests/                       # Test suite
│   └── requirements.txt
│
├── DATASET_CATALOG.md               # Data source documentation
├── ML_DESIGN.md                     # ML model design document
└── README.md                        # This file
```

---

## 🚀 Deployment

### Live URLs

| Service | URL |
|---------|-----|
| **Frontend** | https://ner-logistics-vetha-narayanan-g.vercel.app |
| **Backend API** | https://ner-logistics-1.onrender.com |
| **API Documentation** | https://ner-logistics-1.onrender.com/docs |

### Local Development

#### Backend
```bash
cd ner-logistics-backend
pip install -r requirements.txt
cp .env.example .env  # Configure database URL, JWT secret
uvicorn app.main:app --reload --port 8000
```

#### Frontend
```bash
cd ner-logistics-frontend
npm install
npm run dev
```

---

## 🔌 API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/register` | — | Register new user |
| `POST` | `/auth/login` | — | Login (returns JWT) |
| `GET` | `/roads/bbox` | — | Get roads in viewport (GeoJSON) |
| `GET` | `/bridges/` | — | List bridges with conditions |
| `POST` | `/routing/compute` | ✅ | Compute shortest/safest route |
| `GET` | `/routes/` | — | List saved routes |
| `GET` | `/routes/{id}` | — | Route detail with live status |
| `POST` | `/routes/` | Admin | Create saved route |
| `GET` | `/incidents/` | — | List incidents |
| `POST` | `/incidents/` | ✅ | Report new incident |
| `PATCH` | `/incidents/{id}/status` | ✅ | Update incident lifecycle |
| `GET` | `/vehicles/` | — | List vehicles |
| `POST` | `/vehicles/` | ✅ | Register vehicle |
| `GET` | `/risk/predict` | — | ML risk prediction |
| `GET` | `/alerts/` | — | List active alerts |
| `GET` | `/districts/registry` | — | NER district registry |
| `GET` | `/weather/current` | — | Current weather data |

---

## 🧠 Key Algorithms

### 1. Vertex-Sharing Road Graph Topology
- Extracts **all coordinate vertices** from OSM LineStrings
- Identifies shared vertices between roads (exact match at 7 decimal places ≈ 1.1cm)
- Builds a NetworkX `DiGraph` with ~30,000+ nodes for routing

### 2. Island Stitching Algorithm
- After building the raw graph, detects all disconnected components
- Uses a **spatial grid index** (O(1) lookup) to find the nearest main-network node
- Adds virtual bridge edges to ensure **100% connectivity** — zero NO_ROUTE errors

### 3. Three-Layer Resilient Routing
1. **Layer 1**: Corridor bbox (0.40°) + connected-component-aware snapping
2. **Layer 2**: Wide corridor fallback (0.80°) with re-snap
3. **Layer 3**: Full graph (no bbox) — guaranteed route if one exists

### 4. Multi-Factor Risk Scoring
```
risk_score = f(rainfall_mm, road_condition, bridge_condition, 
               recent_incidents, terrain_difficulty)
```
- Tier 1: Weighted heuristic formula (instant)
- Tier 2: Gradient Boosting ML model (trained on historical data)

---

## 📊 Data Coverage

| Data | Count | Source |
|------|-------|--------|
| Roads | 227,000+ | OpenStreetMap (NER extract) |
| Bridges | 50+ | Seeded + field data |
| Districts | 120+ | All 8 NER states |
| Weather Stations | Real-time | Open-Meteo API |
| NER States | 8 | Assam, Arunachal Pradesh, Manipur, Meghalaya, Mizoram, Nagaland, Sikkim, Tripura |

---

## 👥 Roles & Permissions

| Feature | Admin | Field Official |
|---------|-------|----------------|
| View GIS Dashboard | ✅ | ✅ |
| Calculate Routes | ✅ | ✅ |
| View Saved Routes | ✅ | ✅ |
| Create/Delete Saved Routes | ✅ | ❌ |
| Report Incidents | ✅ | ✅ |
| Manage Incident Status | ✅ | ✅ |
| Register Vehicles | ✅ | ✅ |
| View Alerts | ✅ | ✅ |

---

## 🔄 Incident → Road Status Flow

```
Field Official reports: "Landslide on Road #5432" (severity: high)
        ↓
Auto-update: Road #5432 → status = 'blocked' 🔴
        ↓
Graph cache invalidated → next route avoids this road
        ↓
Admin resolves incident
        ↓
Auto-restore: Road #5432 → status = 'open' 🟢
        ↓
Graph cache invalidated → road available for routing again
```

---

## 📄 License

This project is developed as part of **Smart India Hackathon 2026 (SIH26002)**.

---

<p align="center">
  <b>Built with ❤️ for North Eastern Region of India</b><br>
  <i>Improving transportation accessibility through AI-powered logistics intelligence</i>
</p>
