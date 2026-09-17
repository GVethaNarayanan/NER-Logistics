# SIH26002 — NER Smart Logistics & Accessibility Intelligence Platform (Backend Starter)

Tested, working FastAPI backend skeleton for the AI-Based Smart Logistics and
Accessibility Intelligence Platform for the North Eastern Region. This is a
starting point, not the finished product — it's meant to save you the first
1-2 days of setup so you can spend your 15 days on the parts that actually
need engineering judgment.

## What's already working
- FastAPI app with routers for roads, bridges, weather, incidents, vehicles,
  risk prediction, and alerts
- SQLAlchemy models matching the fields in your DATA_SOURCES.md
- SQLite by default (zero setup) — switch to Postgres by setting DATABASE_URL
- Tier 1 risk engine (app/services/risk_engine.py) — transparent, weighted,
  no training data needed, returns a score/level/explanation exactly like
  the example in your ML_DESIGN.md
- Tier 2 ML training script (ml/train_model.py) — trains Logistic Regression
  + Random Forest, currently bootstrapped on synthetic data generated from
  the Tier 1 rules so it runs today; swap in real events as you compile them
- Open-Meteo weather client (free, no API key) for current/forecast/historical
- OSM road-network fetch script for all 8 NER capitals

## Quickstart
```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env            # optional — SQLite works with no .env at all
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs for interactive Swagger UI to test every
endpoint immediately.

## Pull real data
```bash
python scripts/fetch_weather.py        # current+forecast for 8 NER capitals
python scripts/fetch_osm_roads.py      # road network CSVs for 8 NER capitals
```

## Compile your historical disruption dataset (the critical, non-optional task)
Copy `data/historical_disruptions.csv.example` to
`data/historical_disruptions.csv` and add ~50-100 real rows sourced from
NDMA situation reports, ASDMA bulletins, BRO advisories, and news search —
one focused day, per the plan. Then:
```bash
python ml/train_model.py
```

## Deploy
```bash
docker build -t ner-logistics-backend .
docker run -p 8000:8000 --env-file .env ner-logistics-backend
```

## Not included here (by design — see PROJECT_SCOPE.md "Future Scope")
RAG assistant, AI agents, computer vision, IoT sensors, satellite data,
multi-agent decision-making. Keep these out of the 15-day build.

## Frontend
This backend is API-only. Scaffold the frontend separately:
```bash
npm create vite@latest ner-logistics-frontend -- --template react-ts
cd ner-logistics-frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npx shadcn@latest init
npm install react-leaflet leaflet axios react-i18next i18next
```
