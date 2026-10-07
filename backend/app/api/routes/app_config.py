"""Runtime, non-secret configuration for the signed-in frontend.

Served by the API (not baked into the Next.js build as NEXT_PUBLIC_*), so
changing e.g. QUOTE_BUILDER_URL takes effect with a backend restart only.
Never put credentials here.
"""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["config"])


class AppConfigOut(BaseModel):
    quote_builder_url: str | None


def _safe_external_url(value: str) -> str | None:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return value
    return None


@router.get("/app-config", response_model=AppConfigOut)
def app_config(current_user: User = Depends(get_current_user)) -> AppConfigOut:
    return AppConfigOut(quote_builder_url=_safe_external_url(get_settings().quote_builder_url))
