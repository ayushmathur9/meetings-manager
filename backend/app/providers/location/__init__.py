from app.providers.location.base import (
    DistanceResult,
    GeocodeResult,
    LocationCandidate,
    LocationProvider,
    LocationProviderError,
    TravelTimeResult,
)
from app.providers.location.fallback import FallbackLocationProvider
from app.providers.location.google_maps import GoogleMapsLocationProvider
from app.providers.location.mapbox import MapboxLocationProvider

__all__ = [
    "DistanceResult",
    "GeocodeResult",
    "LocationCandidate",
    "LocationProvider",
    "LocationProviderError",
    "TravelTimeResult",
    "GoogleMapsLocationProvider",
    "MapboxLocationProvider",
    "FallbackLocationProvider",
]

_PLACEHOLDER_VALUES = {"", "REPLACE_WITH_REAL_KEY"}


def get_location_provider() -> LocationProvider:
    """Returns the active LocationProvider implementation.

    Provider choice is driven by `settings.map_provider` ("mapbox" | "google")
    so switching providers never touches business logic — every caller only
    depends on the LocationProvider interface.

    Falls back to a distance-estimate-only provider when the configured
    provider has no real credential set, so the rest of the app (radius
    search, route sequencing) remains testable before a key is provisioned.
    The fallback never fabricates verified addresses — it only estimates
    distance/time using straight-line geometry.
    """
    from app.core.config import get_settings

    settings = get_settings()

    if settings.map_provider == "google":
        if settings.google_maps_api_key in _PLACEHOLDER_VALUES:
            return FallbackLocationProvider()
        return GoogleMapsLocationProvider()

    # default: mapbox
    if settings.mapbox_access_token in _PLACEHOLDER_VALUES:
        return FallbackLocationProvider()
    return MapboxLocationProvider()
