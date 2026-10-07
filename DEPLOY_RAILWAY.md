# Deploying to Railway

This repo deploys as three Railway services in one project: `backend`, `frontend`, and a managed `Postgres` (PostGIS) database.

## 1. Database

- Add a Postgres service. Railway's default Postgres image does **not** include PostGIS — add PostGIS via a custom image (`docker.io/postgis/postgis:16-3.4`) when creating the database service, or run `CREATE EXTENSION postgis;` after provisioning if using an add-on that supports it.
- Railway injects `DATABASE_URL` automatically as `postgresql://...`; the backend now normalizes this to `postgresql+psycopg://...` at startup ([backend/app/core/config.py](backend/app/core/config.py)), so no manual edit is needed.

## 2. Backend service

- Root directory: `backend`
- Builder: Dockerfile (auto-detected via [backend/railway.json](backend/railway.json))
- Required environment variables:
  - `DATABASE_URL` — reference the Postgres service's connection variable
  - `JWT_SECRET` — long random string
  - `JWT_ALGORITHM` = `HS256`
  - `ACCESS_TOKEN_EXPIRE_MINUTES` = `480`
  - `GEOAPIFY_API_KEY` — route planning, travel times and geocoding. **Backend service only** — never add it to the frontend service or any `NEXT_PUBLIC_*` variable.
  - `MAP_PROVIDER` = `geoapify` (geocoding/place search; `mapbox` still works)
  - `MAPBOX_ACCESS_TOKEN` (only needed if `MAP_PROVIDER=mapbox`)
  - Optional: `GEOAPIFY_ROUTE_PLANNER_ENABLED` (default `true`), `ROUTE_MAX_STOPS` (default `25`), `GEOAPIFY_TIMEOUT_SECONDS` (default `15`)
  - `BACKEND_CORS_ORIGINS` — the frontend's public Railway URL (e.g. `https://<frontend>.up.railway.app`)
  - `ENVIRONMENT` = `production`
- Railway sets `PORT` automatically; the Dockerfile's `CMD` already binds `uvicorn` to it, and runs `alembic upgrade head` on every boot.
- Health check path: `/health` (already configured in railway.json).

## 3. Frontend service

- Root directory: `frontend`
- Builder: Dockerfile (auto-detected via [frontend/railway.json](frontend/railway.json))
- Build-time variable (must be set as a **build** arg, since Next.js inlines `NEXT_PUBLIC_*` at build time):
  - `NEXT_PUBLIC_API_BASE_URL` — the backend's public Railway URL
  - `NEXT_PUBLIC_MAP_PROVIDER` = `mapbox`
  - `NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN`
- Railway sets `PORT` automatically; the Dockerfile's `CMD` passes it to `next start`.

## 4. Deploy order

1. Provision Postgres, enable PostGIS.
2. Deploy backend, set its env vars, confirm `/health` responds and migrations ran.
3. Deploy frontend with `NEXT_PUBLIC_API_BASE_URL` pointing at the backend's public URL.
4. Update `BACKEND_CORS_ORIGINS` on the backend to the frontend's final public URL and redeploy.

## Route planner rollout

The sales-day planner adds one migration (`3529ae572fa9_sales_day_route_planner`). It is additive: new nullable columns, a `prospect_priority` enum defaulting to `MEDIUM`, and a backfill of existing route stops. It runs automatically through `alembic upgrade head` on boot.

1. Add `GEOAPIFY_API_KEY` (and `MAP_PROVIDER=geoapify`) to the **backend** service variables.
2. Redeploy the backend and confirm `/health` responds. The deploy log should show `Running upgrade 84ab1f77445b -> 3529ae572fa9`.
3. Redeploy the frontend. It needs no new variables.
4. Optional: unverified company addresses are retried automatically in the background (every 6 hours by default — see `LOCATION_SWEEP_*` in `.env.example`). To force an immediate pass over all of them, e.g. right after setting `GEOAPIFY_API_KEY`, open a Railway shell on the backend and run `python -m app.geocode_pending`.
5. Smoke test: open Routes, select prospects, click **Generate Optimized Route**, then save. Backend logs should show `app.geoapify ... -> 200` lines.

See [docs/ROUTE_PLANNER.md](docs/ROUTE_PLANNER.md) for how planning works, and for troubleshooting.

## CRM sync, business summaries, recordings, Quote Builder rollout

One additive migration (`c41f8e2d7a55_crm_research_recordings`): nullable CRM columns on `companies`/`contacts` plus new tables `bigin_sync_state`, `bigin_sync_runs`, `company_research`, `company_research_sources`, `meeting_recordings` and `meeting_transcripts`. It runs automatically on boot.

1. **Storage bucket (recordings).** In the Railway project, add a **Bucket** (it's private by default; objects are only served through presigned URLs the API issues). On the **backend** service set:
   - `STORAGE_BACKEND` = `s3`
   - `S3_BUCKET` = `${{<bucket>.BUCKET}}`
   - `S3_ENDPOINT_URL` = `${{<bucket>.ENDPOINT}}`
   - `S3_REGION` = `${{<bucket>.REGION}}`
   - `S3_ACCESS_KEY_ID` = `${{<bucket>.ACCESS_KEY_ID}}`
   - `S3_SECRET_ACCESS_KEY` = `${{<bucket>.SECRET_ACCESS_KEY}}`
   - If uploads fail with an addressing or DNS error, set `S3_FORCE_PATH_STYLE=true`.

   Don't use `STORAGE_BACKEND=local` on Railway. The container filesystem is wiped on every deploy.
2. **Transcription.** Set `TRANSCRIPTION_PROVIDER=assemblyai` and `ASSEMBLYAI_API_KEY`. AssemblyAI downloads the audio straight from the bucket through a 15-minute presigned URL. In the AssemblyAI dashboard, opt out of model training and set a data-retention TTL. The app also deletes each transcript from AssemblyAI once it's stored (`ASSEMBLYAI_DELETE_AFTER_COMPLETE`, default `true`).
3. **Business summaries.** Set `ANTHROPIC_API_KEY`. Optional overrides: `SUMMARY_MODEL` (default `claude-opus-5`) and `RESEARCH_STALE_DAYS` (default 90).
4. **Bigin.**
   - Set `BIGIN_CLIENT_ID`, `BIGIN_CLIENT_SECRET` and `BIGIN_REFRESH_TOKEN`. For an org outside the US data center, also set `BIGIN_ACCOUNTS_URL` and `BIGIN_API_DOMAIN`.
   - To receive instant updates, set `PUBLIC_API_BASE_URL` to the backend's public URL. The app registers and renews the Bigin notification channel at `/integrations/bigin/notifications` on its own.
   - Reconciliation runs every `BIGIN_SYNC_INTERVAL_MINUTES` (default 30) either way.
5. **Quote Builder.** Set `QUOTE_BUILDER_URL` on the **backend** service. It's served to signed-in users at runtime, so the frontend doesn't need a rebuild.
6. **Redeploy** the backend, then the frontend (no new frontend variables). Open **CRM Sync** and click **Sync Now**. The page shows *Connected* only after a real Bigin API call succeeds.

Every secret above belongs on the **backend** service only. None of them may be a `NEXT_PUBLIC_*` variable.

Background jobs (Bigin sync, research, transcription polling) run inside the backend process. A Postgres advisory lock ensures only one replica runs each scheduled job, and job state lives in the database, so a redeploy resumes unfinished work.

## Notes

- No more `/api/backend` path-prefix rewriting — that was only needed for Vercel's single-domain routing. Each Railway service gets its own URL, and the frontend already calls the backend directly via `NEXT_PUBLIC_API_BASE_URL` ([frontend/src/lib/api/client.ts](frontend/src/lib/api/client.ts)).
- `vercel.json` has been removed; the project no longer targets Vercel.
