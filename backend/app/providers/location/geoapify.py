"""Geoapify implementation of LocationProvider.

A thin adapter: every HTTP call is delegated to ``app.services.geoapify`` so
Geoapify communication stays centralized in one module. Selected with
``MAP_PROVIDER=geoapify`` (geocoding, place search, travel times); route
planning uses Geoapify whenever GEOAPIFY_API_KEY is set, regardless of
MAP_PROVIDER.
"""

import urllib.parse

from app.providers.location.base import (
    DistanceResult,
    GeocodeResult,
    LocationProvider,
    LocationProviderError,
    TravelTimeResult,
)


def _client():
    # Imported lazily: app.services.geoapify imports this package's base module.
    from app.services.geoapify import get_geoapify_client

    return get_geoapify_client()


class GeoapifyLocationProvider(LocationProvider):
    name = "geoapify"

    def search_business(self, query: str, *, near=None) -> GeocodeResult:
        # Geoapify's geocoder resolves "<business name> <address>" queries to
        # amenities/buildings directly, so business search and address
        # geocoding share one endpoint.
        return GeocodeResult(candidates=_client().geocode_address(query), query=query, provider=self.name)

    def geocode_address(self, address: str) -> GeocodeResult:
        return GeocodeResult(candidates=_client().geocode_address(address), query=address, provider=self.name)

    def geocode_structured(self, *, street, city=None, state=None, postal_code=None, country=None) -> GeocodeResult:
        candidates = _client().geocode_structured(street=street, city=city, state=state, postal_code=postal_code)
        query = ", ".join(p for p in [street, city, state, postal_code] if p)
        return GeocodeResult(candidates=candidates, query=query, provider=self.name)

    def reverse_geocode(self, latitude: float, longitude: float) -> GeocodeResult:
        return GeocodeResult(
            candidates=_client().reverse_geocode(latitude, longitude),
            query=f"{latitude},{longitude}",
            provider=self.name,
        )

    def calculate_distance(self, origin, destination) -> DistanceResult:
        travel = self.calculate_travel_time(origin, destination)
        return DistanceResult(distance_meters=travel.distance_meters, origin=origin, destination=destination)

    def calculate_travel_time(self, origin, destination, *, mode: str = "driving") -> TravelTimeResult:
        result = self.calculate_travel_time_matrix([origin], [destination], mode=mode)[0][0]
        if result is None:
            raise LocationProviderError("No route found between origin and destination")
        return result

    def calculate_travel_time_matrix(self, origins, destinations, *, mode: str = "driving"):
        return _client().get_route_matrix(list(origins), list(destinations), mode=mode)

    def create_navigation_link(self, destination, *, origin=None) -> str:
        # Navigation is handed off to Google Maps deep links (works on every
        # phone) — same behaviour as the other providers.
        def fmt(value):
            if isinstance(value, tuple):
                return f"{value[0]},{value[1]}"
            return value

        params = {"api": "1", "destination": fmt(destination), "travelmode": "driving"}
        if origin is not None:
            params["origin"] = fmt(origin)
        return f"https://www.google.com/maps/dir/?{urllib.parse.urlencode(params)}"
