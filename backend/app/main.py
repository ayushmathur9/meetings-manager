import logging
import traceback  # noqa: F401 - used by exception handler below
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    activity,
    app_config,
    auth,
    companies,
    contacts,
    crm_sync,
    imports,
    locations,
    meetings,
    navigation,
    prospects,
    recordings,
    research,
    routes_router,
    settings as settings_router,
    users,
)
from app.core.config import get_settings
from app.services.background import PeriodicTask, start_periodic_tasks
from app.services.bigin_sync import scheduled_sync
from app.services.location_sweep import start_location_sweeper
from app.services.recording_service import poll_pending_recordings

settings = get_settings()

_TRANSCRIPTION_POLL_LOCK = 0x7A5C21B


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop_sweeper = start_location_sweeper()
    stop_tasks = start_periodic_tasks([
        # Bigin reconciliation + notification-channel renewal (it takes its
        # own sync lock, shared with manual/webhook syncs).
        PeriodicTask("bigin-sync", settings.bigin_sync_interval_minutes * 60, scheduled_sync, startup_delay_seconds=90),
        PeriodicTask(
            "transcription-poll",
            settings.transcription_poll_interval_seconds,
            poll_pending_recordings,
            startup_delay_seconds=20,
            lock_key=_TRANSCRIPTION_POLL_LOCK,
        ),
    ])
    yield
    for stop in (stop_sweeper, stop_tasks):
        if stop is not None:
            stop.set()


app = FastAPI(title="Meetings Manager API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(contacts.router)
api_router.include_router(imports.router)
api_router.include_router(prospects.router)
api_router.include_router(locations.router)
api_router.include_router(meetings.router)
api_router.include_router(routes_router.router)
api_router.include_router(navigation.router)
api_router.include_router(users.router)
api_router.include_router(settings_router.router)
api_router.include_router(activity.router)
api_router.include_router(crm_sync.router)
api_router.include_router(crm_sync.webhook_router)
api_router.include_router(research.router)
api_router.include_router(recordings.router)
api_router.include_router(app_config.router)
app.include_router(api_router)

# Outbound Geoapify calls (endpoint, status, latency — never the API key) and
# background location-sweep summaries at INFO.
_geoapify_handler = logging.StreamHandler()
_geoapify_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
for _name in ("app.geoapify", "app.location_sweep", "app.bigin", "app.bigin_sync", "app.research",
              "app.transcription", "app.background"):
    _logger = logging.getLogger(_name)
    _logger.setLevel(logging.INFO)
    _logger.addHandler(_geoapify_handler)

_error_logger = logging.getLogger("app.errors")
_error_logger.setLevel(logging.ERROR)
_log_formatter = logging.Formatter("%(asctime)s %(message)s")
try:
    _error_handler: logging.Handler = logging.FileHandler("server_errors.log", encoding="utf-8")
except OSError:
    _error_handler = logging.StreamHandler()
_error_handler.setFormatter(_log_formatter)
_error_logger.addHandler(_error_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _error_logger.error(
        "Unhandled error on %s %s\n%s",
        request.method,
        request.url.path,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
