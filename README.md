# Meetings Manager

Field-sales prospect, meeting and route management for Sam IT Solutions.

- **Frontend:** Next.js + Tailwind (`frontend/`)
- **Backend:** FastAPI + SQLAlchemy + Alembic (`backend/`)
- **Database:** PostgreSQL + PostGIS

## Documentation

- [Sales Day Route Planner (Geoapify)](docs/ROUTE_PLANNER.md): radius filtering, optimization, scheduling, API, local setup and troubleshooting
- [CRM sync, business summaries, meeting recordings](docs/CRM_SUMMARIES_RECORDINGS.md): Bigin sync, website-sourced AI overviews, recording + transcription, Quote Builder link
- [Deploying to Railway](DEPLOY_RAILWAY.md)

## Quick start

```bash
docker compose up -d db
cp .env.example .env            # fill in GEOAPIFY_API_KEY and the Mapbox tokens
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/alembic upgrade head && .venv/Scripts/python -m app.seed
.venv/Scripts/python -m uvicorn app.main:app --port 8001
cd ../frontend && pnpm install && pnpm dev    # http://localhost:3001
```

On macOS/Linux, use `.venv/bin/` instead of `.venv/Scripts/`. The seed users are
`admin@samitsolutions.com` and `sales@samitsolutions.com` (password `Test@123`).
