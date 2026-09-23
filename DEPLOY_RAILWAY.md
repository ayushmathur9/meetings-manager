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
  - `MAP_PROVIDER` = `mapbox`
  - `MAPBOX_ACCESS_TOKEN`
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

## Notes

- No more `/api/backend` path-prefix rewriting — that was only needed for Vercel's single-domain routing. Each Railway service gets its own URL, and the frontend already calls the backend directly via `NEXT_PUBLIC_API_BASE_URL` ([frontend/src/lib/api/client.ts](frontend/src/lib/api/client.ts)).
- `vercel.json` has been removed; the project no longer targets Vercel.
