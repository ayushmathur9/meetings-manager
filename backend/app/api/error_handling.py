"""Shared API-layer error translation for outbound calls to the map/location
provider — any endpoint that talks to Mapbox/Google can wrap its call with
`translate_provider_errors()` to get a clean, honest 502 instead of an
unhandled 500.
"""

import logging
from contextlib import contextmanager

import httpx
from fastapi import HTTPException, status

from app.providers.location import LocationProviderError

_error_logger = logging.getLogger("app.errors")


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
    except (httpx.HTTPError, LocationProviderError) as exc:
        _error_logger.error("Location provider call failed: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The map/location service is unavailable right now. Please try again shortly "
            "or contact an administrator if this persists.",
        )
