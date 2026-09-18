import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    activity,
    auth,
    companies,
    contacts,
    imports,
    locations,
    meetings,
    navigation,
    prospects,
    routes_router,
    settings as settings_router,
    users,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Meetings Manager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(contacts.router)
app.include_router(imports.router)
app.include_router(prospects.router)
app.include_router(locations.router)
app.include_router(meetings.router)
app.include_router(routes_router.router)
app.include_router(navigation.router)
app.include_router(users.router)
app.include_router(settings_router.router)
app.include_router(activity.router)

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
