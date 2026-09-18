"""Google Maps Platform implementation of LocationProvider.

Uses the Geocoding API, Places API (Find Place / Text Search), and Distance
Matrix API over plain HTTP (no heavyweight SDK dependency). All parsing here
stays local to this file — nothing outside `app/providers/location` should
import `googlemaps` or touch Google-specific response shapes.
"""

import urllib.parse

import httpx

from app.core.config import get_settings
from app.providers.location.base import (
    DistanceResult,
    GeocodeResult,
    LocationCandidate,
    LocationProvider,
    LocationProviderError,
    TravelTimeResult,
)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

_ADDRESS_COMPONENT_MAP = {
    "street_number": "street_number",
    "route": "route",
    "locality": "city",
    "administrative_area_level_1": "state",
    "postal_code": "postal_code",
    "country": "country",
}


class GoogleMapsLocationProvider(LocationProvider):
    name = "google_maps"

    def __init__(self, api_key: str | None = None, timeout: float = 10.0) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.google_maps_api_key
        self._timeout = timeout

    def _get(self, url: str, params: dict) -> dict:
        params = {**params, "key": self._api_key}
        response = httpx.get(url, params=params, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _parse_address_components(self, components: list[dict]) -> dict:
        parsed: dict[str, str] = {}
        street_number = None
        route = None
        for component in components:
            types = component.get("types", [])
            for google_type, field in _ADDRESS_COMPONENT_MAP.items():
                if google_type in types:
                    if field == "street_number":
                        street_number = component["long_name"]
                    elif field == "route":
                        route = component["long_name"]
                    else:
                        parsed[field] = component["long_name"]
        if street_number or route:
            parsed["address_line_1"] = " ".join(filter(None, [street_number, route]))
        return parsed

    def _geocode_result_to_candidate(self, result: dict, confidence: str) -> LocationCandidate:
        location = result["geometry"]["location"]
        components = self._parse_address_components(result.get("address_components", []))
        return LocationCandidate(
            formatted_address=result.get("formatted_address", ""),
            latitude=location["lat"],
            longitude=location["lng"],
            place_id=result.get("place_id"),
            confidence=confidence,
            **components,
        )

    def search_business(
        self, query: str, *, near: tuple[float, float] | None = None
    ) -> GeocodeResult:
        params: dict = {
            "input": query,
            "inputtype": "textquery",
            "fields": "place_id,formatted_address,geometry,name",
        }
        if near is not None:
            params["locationbias"] = f"circle:50000@{near[0]},{near[1]}"

        data = self._get(_FIND_PLACE_URL, params)
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise LocationProviderError(f"Google Places error: {status}")

        candidates: list[LocationCandidate] = []
        for candidate_data in data.get("candidates", []):
            place_id = candidate_data.get("place_id")
            details = self._get_place_details(place_id) if place_id else None
            if details is not None:
                candidates.append(details)
                continue
            location = candidate_data["geometry"]["location"]
            candidates.append(
                LocationCandidate(
                    formatted_address=candidate_data.get("formatted_address", ""),
                    latitude=location["lat"],
                    longitude=location["lng"],
                    place_id=place_id,
                    name=candidate_data.get("name"),
                    confidence="medium" if len(data.get("candidates", [])) == 1 else "low",
                )
            )
        return GeocodeResult(candidates=candidates, query=query, provider=self.name)

    def _get_place_details(self, place_id: str) -> LocationCandidate | None:
        data = self._get(
            _PLACE_DETAILS_URL,
            {"place_id": place_id, "fields": "name,formatted_address,geometry,address_component"},
        )
        if data.get("status") != "OK":
            return None
        result = data["result"]
        location = result["geometry"]["location"]
        components = self._parse_address_components(result.get("address_components", []))
        return LocationCandidate(
            formatted_address=result.get("formatted_address", ""),
            latitude=location["lat"],
            longitude=location["lng"],
            place_id=place_id,
            name=result.get("name"),
            confidence="high",
            **components,
        )

    def geocode_address(self, address: str) -> GeocodeResult:
        data = self._get(_GEOCODE_URL, {"address": address})
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise LocationProviderError(f"Google Geocoding error: {status}")

        results = data.get("results", [])
        confidence = "high" if len(results) == 1 else "low"
        candidates = [self._geocode_result_to_candidate(r, confidence) for r in results]
        return GeocodeResult(candidates=candidates, query=address, provider=self.name)

    def reverse_geocode(self, latitude: float, longitude: float) -> GeocodeResult:
        data = self._get(_GEOCODE_URL, {"latlng": f"{latitude},{longitude}"})
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise LocationProviderError(f"Google Reverse Geocoding error: {status}")

        results = data.get("results", [])
        confidence = "high" if results else "unknown"
        candidates = [self._geocode_result_to_candidate(r, confidence) for r in results]
        query = f"{latitude},{longitude}"
        return GeocodeResult(candidates=candidates, query=query, provider=self.name)

    def calculate_distance(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> DistanceResult:
        travel = self.calculate_travel_time(origin, destination)
        return DistanceResult(
            distance_meters=travel.distance_meters, origin=origin, destination=destination
        )

    def calculate_travel_time(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        mode: str = "driving",
    ) -> TravelTimeResult:
        matrix = self.calculate_travel_time_matrix([origin], [destination], mode=mode)
        result = matrix[0][0]
        if result is None:
            raise LocationProviderError("No route found between origin and destination")
        return result

    def calculate_travel_time_matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
        *,
        mode: str = "driving",
    ) -> list[list[TravelTimeResult | None]]:
        origins_param = "|".join(f"{lat},{lng}" for lat, lng in origins)
        destinations_param = "|".join(f"{lat},{lng}" for lat, lng in destinations)

        data = self._get(
            _DISTANCE_MATRIX_URL,
            {"origins": origins_param, "destinations": destinations_param, "mode": mode},
        )
        if data.get("status") != "OK":
            raise LocationProviderError(f"Google Distance Matrix error: {data.get('status')}")

        matrix: list[list[TravelTimeResult | None]] = []
        rows = data.get("rows", [])
        for i, row in enumerate(rows):
            row_results: list[TravelTimeResult | None] = []
            for j, element in enumerate(row.get("elements", [])):
                if element.get("status") != "OK":
                    row_results.append(None)
                    continue
                row_results.append(
                    TravelTimeResult(
                        duration_seconds=element["duration"]["value"],
                        distance_meters=element["distance"]["value"],
                        origin=origins[i],
                        destination=destinations[j],
                        mode=mode,
                    )
                )
            matrix.append(row_results)
        return matrix

    def create_navigation_link(
        self,
        destination: tuple[float, float] | str,
        *,
        origin: tuple[float, float] | str | None = None,
    ) -> str:
        def fmt(value: tuple[float, float] | str) -> str:
            if isinstance(value, tuple):
                return f"{value[0]},{value[1]}"
            return value

        params = {"api": "1", "destination": fmt(destination)}
        if origin is not None:
            params["origin"] = fmt(origin)
        return f"https://www.google.com/maps/dir/?{urllib.parse.urlencode(params)}"
