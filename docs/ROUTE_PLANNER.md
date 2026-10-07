# Sales Day Route Planner (Geoapify)

The route planner turns a list of prospects into a timed sales day: optimized
stop order, real road travel times, meeting slots inside working hours, a road
route on the map, and a saved plan that syncs the day's meetings.

**Geoapify is only the geospatial engine.** CRM data, permissions, priorities,
meeting durations, working hours, scheduling and persistence all stay in this
application.

```
Next.js  ──►  FastAPI  ──►  Geoapify
   ▲            │  ▲            │
   └────────────┘  └────────────┘
```

The browser never talks to Geoapify and never sees the key.

## 1. How Geoapify is integrated

All Geoapify HTTP traffic lives in one module:
[backend/app/services/geoapify.py](../backend/app/services/geoapify.py).

| Function | Geoapify API | Used for |
| --- | --- | --- |
| `geocode_address()` | Geocoding `/v1/geocode/search` | Locating companies that have no coordinates, place search |
| `reverse_geocode()` | Reverse geocoding `/v1/geocode/reverse` | Coordinates → address |
| `get_route_matrix()` | Route Matrix `/v1/routematrix` | Travel time/distance between every pair of stops |
| `optimize_route()` | Route Planner `/v1/routeplanner` | An order suggestion that competes with the in-app optimizer |
| `get_route()` | Routing `/v1/routing` | Road geometry for the final order (drawn on the map) |

Behaviour shared by every call:

- **Validation before any request.** Out-of-range, non-numeric or `(0, 0)` coordinates are rejected locally. Identical points are de-duplicated before a matrix request.
- **Timeouts and one retry.** The timeout is `GEOAPIFY_TIMEOUT_SECONDS` (default 15 s). Timeouts, network errors and 5xx responses are retried once, since every call is idempotent. 4xx responses are not retried.
- **Typed errors with safe messages.** Each `GeoapifyError` subclass carries a `user_message` that can be shown to users. Raw Geoapify responses are logged on the server only.

| Error | HTTP status returned by our API |
| --- | --- |
| `GeoapifyNotConfiguredError` | 503 |
| `GeoapifyAuthError` | 502 |
| `GeoapifyRateLimitError` | 429 |
| `GeoapifyUnavailableError` | 502 |
| `GeoapifyBadRequestError` / `GeoapifyNoRouteError` | 422 |

- **Caching.** Results are held in a process-local TTL cache (`GEOAPIFY_CACHE_TTL_SECONDS`, default 6 h), keyed by rounded coordinates. Re-planning the same stops, or toggling back to a previous order, doesn't spend API credits.
- **Logging.** Calls are logged at INFO by the `app.geoapify` logger as endpoint, status and latency. The API key is never logged. Provider error messages are also scrubbed of `apiKey=` / `access_token=` before they are written to `server_errors.log`.

With `MAP_PROVIDER=geoapify`, the existing `LocationProvider` abstraction uses
[GeoapifyLocationProvider](../backend/app/providers/location/geoapify.py).
That applies to Excel-import verification, the location search box and
`python -m app.geocode_pending`. The adapter delegates to the same service
module.

## 2. Environment variables

| Variable | Where | Required | Notes |
| --- | --- | --- | --- |
| `GEOAPIFY_API_KEY` | backend | yes | Server-side only. Never `NEXT_PUBLIC_*`. |
| `MAP_PROVIDER` | backend | no | `geoapify` (recommended), `mapbox` or `google`. Controls geocoding/place search. Routing uses Geoapify whenever the key is set. |
| `GEOAPIFY_TIMEOUT_SECONDS` | backend | no | Default `15`. |
| `GEOAPIFY_CACHE_TTL_SECONDS` | backend | no | Default `21600` (6 h). |
| `GEOAPIFY_ROUTE_PLANNER_ENABLED` | backend | no | Default `true`. Set to `false` to skip the Route Planner call and use only the in-app optimizer, which saves credits. |
| `ROUTE_MAX_STOPS` | backend | no | Default `25` stops per day. |
| `NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN` | frontend (build) | yes, for the map | Map tiles only. Unchanged. |

Without `GEOAPIFY_API_KEY`, travel times fall back to the configured
`MAP_PROVIDER` road matrix (for example Mapbox), and the plan carries a
warning. If no road-network provider is configured at all, planning fails
with a clear message. It never silently uses straight-line distances.

## 3. Radius filtering (PostGIS)

`POST /routes/preview` runs one PostGIS query. Distance is computed with
`ST_Distance` / `ST_DWithin` on `geography`, which gives true metres on the
spheroid. The query classifies each prospect as:

- **inside**: within the radius;
- **outside**: has coordinates, but is beyond the radius;
- **missing_coordinates**: no usable latitude/longitude.

No external API is called. Salespeople see only prospects assigned to them.
Admins choose a salesperson, and can switch the list to all companies.

Only the prospects the user actually selects are ever sent to Geoapify.
The radius is a hard filter: prospects outside it can't be selected in the UI, and if the API receives
one anyway it is left out and listed under `unscheduled` with reason `outside_radius`.

From the prospect list, **Locate** (single or "Locate all") calls
`POST /routes/geocode-missing`. That runs the same verification rules as Excel
import:

- A match is only accepted when it's a single, high-confidence result whose city and state agree with the imported ones.
- Ambiguous results are marked *needs review* rather than guessed.
- An already verified location is never overwritten by an automated lookup.

## 4. How optimization works

Pure logic in
[backend/app/services/route_optimizer.py](../backend/app/services/route_optimizer.py).

1. One matrix is built over the start and every selected stop inside the radius. There is no end location: the day ends at the last meeting.
2. Candidate orders are evaluated by *simulating the whole day*. They are compared by this cost, in order:
   1. unreachable stops;
   2. lateness to meetings that already have a committed time;
   3. minutes past working hours;
   4. end-of-day time;
   5. total driving.
3. The order search depends on how many stops there are:
   - **7 stops or fewer:** an exhaustive search over every order.
   - **More than 7:** nearest-neighbour, then 2-opt and or-opt local search.
4. When enabled (3+ stops), Geoapify's Route Planner suggests an order. It is scored with the same cost, and the better order wins. The plan reports which engine produced the order (`geoapify_route_planner`, `local` or `manual`).
5. The start is always first; the meetings after it are reordered freely.
6. If the start itself has no road access (e.g. a mountain peak or park chosen from search), planning stops with a clear "start_unreachable" error rather than marking every stop unreachable.

## 5. How scheduling works

Rules, in priority order:

1. **Hard constraints.** Unreachable stops are left out. A meeting already on the calendar at a set time (not created by the planner) keeps that time. The route waits for it, or is flagged as late.
2. **Working hours.** Every meeting must end inside the window. *Allow meetings past working hours* lifts this and flags the overtime.
3. **Fixed start.**
4. **Meeting duration.** There's a default for the day, plus a per-stop override. An optional arrival buffer (parking/check-in) is inserted between arriving and the meeting starting. Meetings start on whole minutes.
5. **Priority (High/Medium/Low on the prospect).** If not everything fits, the lowest-priority stops are left out first. Within the same priority, the stop whose removal saves the most time goes first. Priority never reorders a feasible route at the expense of efficiency.
6. **Route efficiency.**

Stops that don't fit are **never silently dropped**. The plan lists them under
`unscheduled` with a reason, and the first warning reads, for example:
*"6 meetings selected, but only 4 fit within the available time (8:30 AM–4:30 PM)."*

Each scheduled stop has these fields:
- arrival
- meeting start and end
- departure
- drive time and distance from the previous stop
- wait time, lateness, and an outside-hours flag

Totals cover distance, driving, meeting time, and the total day (start to finish).

### Editing and recalculating

- Drag a stop, or use the ↑/↓ buttons, to reorder. Stops can also be removed, have their duration changed, or be added from the prospect list.
- After any edit, the timeline greys out its times. **Recalculate Route** keeps your order (`optimize=false`). **Re-optimize** finds the best order again.

### Saving

- **Save Route** stores:
  - the configuration and ordered stops;
  - times and road geometry;
  - totals, warnings and the unscheduled list;
  - a snapshot of each stop's name, address and coordinates.
- One route is kept per salesperson per day. Saving over an existing day asks for confirmation first.
- Saving also creates or updates the salesperson's meetings for that day. These are flagged `is_planner_generated`, so they appear on *My Meetings* and the dashboard.
- A meeting that was booked by hand is never moved.
- Planner meetings for stops that were removed are deleted, but only if they're still in the *scheduled* state.
- Reopening a saved route shows exactly what was saved. If a company's location has changed since, the route is flagged and **Recalculate** produces a fresh plan; nothing changes until you save.
- **Navigate** opens Google Maps directions to the stop's coordinates.

## 6. API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/routes/preview` | Candidates by radius (PostGIS) |
| POST | `/routes/optimize` | Order (optional) and schedule the selected stops. Not saved. |
| POST | `/routes/geocode-missing` | Locate companies without coordinates |
| GET | `/routes` | Saved routes (salespeople see only their own) |
| POST | `/routes` | Save a plan as the day's route |
| GET | `/routes/{id}` | Reopen a saved route (includes `is_stale` / `location_changed`) |
| PATCH | `/routes/{id}` | Replace the plan, rename, or change status |
| DELETE | `/routes/{id}` | Delete (removes only untouched planner meetings) |
| POST | `/routes/{id}/recalculate` | Re-plan using current locations. Not saved. |
| PATCH | `/prospects/{company_id}/priority` | Set High/Medium/Low |

The existing `/routes/generate`, `/routes/plan`, `/routes/by-date` and
`/routes/{id}/reorder` endpoints are unchanged, apart from new ownership checks.

**Permissions.** Salespeople can plan, view and change only their own routes,
using only prospects assigned to them. Other people's route ids return 404.
Admins have full access.

Structured errors look like this:

```json
{"detail": {"code": "missing_coordinates",
            "message": "Route could not be generated because 2 selected prospects do not have valid coordinates.",
            "companies": [{"company_id": "…", "company_name": "…", "address": "…"}]}}
```

## 7. Running locally

```bash
docker compose up -d db                       # PostGIS on localhost:5433
cp .env.example .env                          # then set GEOAPIFY_API_KEY, MAPBOX tokens
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt pytest   # (bin/ on macOS/Linux)
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.seed
.venv/Scripts/python -m uvicorn app.main:app --port 8001
# new terminal
cd frontend && pnpm install && pnpm dev       # http://localhost:3001
```

To geocode companies that are still missing coordinates (it is safe to re-run):

```bash
cd backend && .venv/Scripts/python -m app.geocode_pending
```

Tests use a separate `meetings_manager_test` database, which is created and
migrated automatically. Geoapify is mocked, so no network calls are made:

```bash
cd backend && .venv/Scripts/python -m pytest app/tests -q
```

## 8. Troubleshooting Geoapify

| Symptom | Likely cause / fix |
| --- | --- |
| "Route optimization is not configured…" (503) | `GEOAPIFY_API_KEY` is missing on the backend service. Set it and redeploy. |
| "The routing service rejected our credentials…" | Invalid or revoked key, or the key is restricted to other domains or IPs. Check it at myprojects.geoapify.com. |
| "…too many requests…" (429) | You hit the plan's rate or credit limit. Wait, or consider disabling the Route Planner call (`GEOAPIFY_ROUTE_PLANNER_ENABLED=false`). |
| "…unavailable right now…" (502) | Timeout or outage, which has already been retried once. Check backend logs for `app.geoapify` lines with status and latency. |
| "…do not have valid coordinates" | Click **Try to locate them**. If a company comes back *needs review*, pick the right match on its prospect page. |
| A stop is "unreachable" | There's no drivable road route. The coordinates are probably wrong (for example, in water). Fix the company location. |
| Map shows markers but no tiles or road line | That's the frontend Mapbox token (`NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN`), not Geoapify. |

Backend logs show each call as, for example,
`INFO app.geoapify Geoapify POST /v1/routematrix -> 200 (412 ms)`.

### End locations

The planner no longer offers an end location: every route ends at the last
meeting. Routes saved earlier with an end still reopen exactly as saved;
recalculating them drops the end.
