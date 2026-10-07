"""Shared API-layer error translation for outbound calls to the map/location
provider — any endpoint that talks to Mapbox/Google can wrap its call with
`translate_provider_errors()` to get a clean, honest 502 instead of an
unhandled 500.
"""

import logging
import re
from contextlib import contextmanager

import httpx
from fastapi import HTTPException, status

from app.providers.location import LocationProviderError
from app.services.geoapify import GeoapifyError, InvalidCoordinatesError

_error_logger = logging.getLogger("app.errors")

# Provider exceptions often embed the request URL, which carries the API key.
_SECRET_PARAM_RE = re.compile(r"(access_token|apiKey|api_key|key)=[^&\s'\"]+", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    return _SECRET_PARAM_RE.sub(lambda m: f"{m.group(1)}=***", text)


@contextmanager
def translate_provider_errors():
    """Turn a location-provider failure (bad/expired API key, provider outage,
    network error) into a clean 502 instead of an unhandled 500.

    An HTTPException raised here still goes through CORSMiddleware normally,
    unlike an exception that escapes to Starlette's global handler — so the
    browser gets a readable error instead of a bare "Failed to fetch". The
    underlying exception (which may embed the request URL, including the API
    key as a query param) is logged server-side only, never sent to the client.
    """
    try:
        yield
    except InvalidCoordinatesError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "invalid_coordinates", "message": str(exc)},
        )
    except GeoapifyError as exc:
        _error_logger.error("Geoapify call failed (%s): %s", exc.code, exc)
        http_status = {
            "routing_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
            "routing_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
            "no_route_found": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "routing_bad_request": status.HTTP_422_UNPROCESSABLE_ENTITY,
        }.get(exc.code, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(http_status, {"code": exc.code, "message": exc.user_message})
    except (httpx.HTTPError, LocationProviderError) as exc:
        _error_logger.error("Location provider call failed: %s", redact_secrets(str(exc)))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The map/location service is unavailable right now. Please try again shortly "
            "or contact an administrator if this persists.",
        )
