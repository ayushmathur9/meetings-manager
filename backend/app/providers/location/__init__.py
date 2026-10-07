from app.providers.location.base import (
    DistanceResult,
    GeocodeResult,
    LocationCandidate,
    LocationProvider,
    LocationProviderError,
    TravelTimeResult,
)
from app.providers.location.fallback import FallbackLocationProvider
from app.providers.location.geoapify import GeoapifyLocationProvider
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
    "GeoapifyLocationProvider",
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

    if settings.map_provider == "geoapify":
        if settings.geoapify_api_key.strip() in _PLACEHOLDER_VALUES | {"your_geoapify_api_key"}:
            return FallbackLocationProvider()
        return GeoapifyLocationProvider()

    if settings.map_provider == "google":
        if settings.google_maps_api_key in _PLACEHOLDER_VALUES:
            return FallbackLocationProvider()
        return GoogleMapsLocationProvider()

    # default: mapbox
    if settings.mapbox_access_token in _PLACEHOLDER_VALUES:
        return FallbackLocationProvider()
    return MapboxLocationProvider()


def get_geocoding_provider() -> LocationProvider:
    """The provider to use for address verification.

    Same as get_location_provider(), except that when the configured
    MAP_PROVIDER has no credential but GEOAPIFY_API_KEY is set, Geoapify is
    used instead of the fallback (which can't verify anything) — matching
    how route planning already uses Geoapify whenever its key is present.
    """
    provider = get_location_provider()
    if provider.name != FallbackLocationProvider.name:
        return provider
    from app.services.geoapify import get_geoapify_client

    if get_geoapify_client().is_configured:
        return GeoapifyLocationProvider()
    return provider
