"""Fallback LocationProvider used when no Google Maps API key is configured
(or a call to Google fails). Never used silently in a way that fabricates a
verified location: geocoding/business-search here return zero candidates
(there is no data to make one up), so companies correctly stay flagged as
"needs verification" until a real API key is wired in.

Distance/travel-time estimates use straight-line (haversine) distance and an
assumed average road speed. This is a practical placeholder so route
generation and travel-time-dependent UI can be exercised end-to-end during
development — it is NOT a substitute for the real Distance Matrix API in
production.
"""

import urllib.parse
from math import asin, cos, radians, sin, sqrt

from app.providers.location.base import (
    DistanceResult,
    GeocodeResult,
    LocationProvider,
    TravelTimeResult,
)

_AVERAGE_SPEED_METERS_PER_SECOND = 11.0  # ~25 mph average, accounting for city driving + lights


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lng2 - lng1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * r * asin(sqrt(a))


class FallbackLocationProvider(LocationProvider):
    """No-API-key-required provider: honest about not being able to verify
    real-world locations/addresses, but still able to support distance-based
    features (radius filtering, route sequencing) using straight-line estimates.
    """

    name = "fallback_estimate"

    def search_business(self, query: str, *, near=None) -> GeocodeResult:
        return GeocodeResult(candidates=[], query=query, provider=self.name)

    def geocode_address(self, address: str) -> GeocodeResult:
        return GeocodeResult(candidates=[], query=address, provider=self.name)

    def reverse_geocode(self, latitude: float, longitude: float) -> GeocodeResult:
        return GeocodeResult(candidates=[], query=f"{latitude},{longitude}", provider=self.name)

    def calculate_distance(self, origin, destination) -> DistanceResult:
        meters = _haversine_meters(origin[0], origin[1], destination[0], destination[1])
        return DistanceResult(distance_meters=meters, origin=origin, destination=destination)

    def calculate_travel_time(self, origin, destination, *, mode: str = "driving") -> TravelTimeResult:
        meters = _haversine_meters(origin[0], origin[1], destination[0], destination[1])
        # Straight-line distance undercounts real road distance; apply a routing factor.
        road_meters = meters * 1.3
        seconds = int(road_meters / _AVERAGE_SPEED_METERS_PER_SECOND)
        return TravelTimeResult(
            duration_seconds=seconds,
            distance_meters=road_meters,
            origin=origin,
            destination=destination,
            mode=mode,
        )

    def calculate_travel_time_matrix(self, origins, destinations, *, mode: str = "driving"):
        return [
            [self.calculate_travel_time(o, d, mode=mode) for d in destinations] for o in origins
        ]

    def create_navigation_link(self, destination, *, origin=None) -> str:
        def fmt(value):
            if isinstance(value, tuple):
                return f"{value[0]},{value[1]}"
            return value

        params = {"api": "1", "destination": fmt(destination)}
        if origin is not None:
            params["origin"] = fmt(origin)
        return f"https://www.google.com/maps/dir/?{urllib.parse.urlencode(params)}"
