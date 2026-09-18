"""Mapbox implementation of LocationProvider.

Uses Mapbox's Geocoding API v6 (forward/reverse/structured), Search Box API
(POI/business search), and Matrix API (batched travel times) over plain HTTP.
No Mapbox SDK dependency — all parsing stays local to this file so nothing
outside `app/providers/location` needs to know about Mapbox response shapes.

Free tier: no credit card required to start, generous monthly quota — see
https://www.mapbox.com/pricing for current limits.
"""

import re
import urllib.parse
import uuid

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

_GEOCODING_URL = "https://api.mapbox.com/search/geocode/v6/forward"
_REVERSE_GEOCODING_URL = "https://api.mapbox.com/search/geocode/v6/reverse"
_SEARCHBOX_SUGGEST_URL = "https://api.mapbox.com/search/searchbox/v1/suggest"
_SEARCHBOX_RETRIEVE_URL = "https://api.mapbox.com/search/searchbox/v1/retrieve"

_MODE_PROFILE = {
    "driving": "driving",
    "walking": "walking",
    "bicycling": "cycling",
}

_HOUSE_NUMBER_RE = re.compile(r"\b(\d+)[A-Za-z]?\b")
_WORD_RE = re.compile(r"[a-z]+")
# Common street-suffix synonyms so "St" vs "Street" doesn't look like a
# mismatch when scoring how well a candidate's address matches the query.
_STREET_SUFFIX_SYNONYMS = {
    "st": "street", "rd": "road", "dr": "drive", "ave": "avenue", "blvd": "boulevard",
    "ln": "lane", "ct": "court", "pkwy": "parkway", "hwy": "highway",
}
# Directional words scored separately: real-world source data is frequently
# inconsistent about these (e.g. a spreadsheet says "Nash St N" for a business
# actually addressed "Nash Street Northwest") — a directional mismatch alone
# should soften the score, not zero it out the way an unrelated street would.
_DIRECTIONALS = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    "north": "north", "south": "south", "east": "east", "west": "west",
    "northeast": "northeast", "northwest": "northwest",
    "southeast": "southeast", "southwest": "southwest",
}


def _address_match_score(query_address: str | None, candidate_address: str | None) -> float:
    """0.0-1.0 score for how well a candidate's street address matches the
    address text that was actually searched for — used because a provider
    returning many *suggestions* for an under-specific query says nothing
    about whether the best candidate is a strong match; only comparing the
    text does. Requires the house number to match exactly (a street-name-only
    match on a different house number is not a real match); the rest of the
    score comes from non-directional street-name word overlap, with a
    directional (N/S/E/W/NE/NW/SE/SW) mismatch only lightly penalized since
    that's a common inconsistency between real-world data sources.
    """
    if not query_address or not candidate_address:
        return 0.0

    def house_number(text: str) -> str | None:
        m = _HOUSE_NUMBER_RE.search(text)
        return m.group(1) if m else None

    def words(text: str) -> tuple[set[str], set[str]]:
        raw = _WORD_RE.findall(text.lower())
        directionals = {_DIRECTIONALS[w] for w in raw if w in _DIRECTIONALS}
        street_words = {_STREET_SUFFIX_SYNONYMS.get(w, w) for w in raw if w not in _DIRECTIONALS}
        return street_words, directionals

    query_house = house_number(query_address)
    candidate_house = house_number(candidate_address)
    if query_house and candidate_house and query_house != candidate_house:
        return 0.0

    query_words, query_dirs = words(query_address)
    candidate_words, candidate_dirs = words(candidate_address)
    if not query_words:
        return 0.0
    overlap = len(query_words & candidate_words) / len(query_words)
    if query_dirs and candidate_dirs and not (query_dirs & candidate_dirs):
        overlap *= 0.9  # directional mismatch: small penalty, not disqualifying
    return overlap


class MapboxLocationProvider(LocationProvider):
    name = "mapbox"

    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        settings = get_settings()
        self._token = access_token or settings.mapbox_access_token
        self._timeout = timeout

    def _get(self, url: str, params: dict) -> dict:
        params = {**params, "access_token": self._token}
        response = httpx.get(url, params=params, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _feature_to_candidate(self, feature: dict, confidence: str) -> LocationCandidate:
        properties = feature.get("properties", {})
        coordinates = feature["geometry"]["coordinates"]  # [lng, lat]
        context = properties.get("context", {})
        return LocationCandidate(
            formatted_address=properties.get("full_address") or properties.get("place_formatted", ""),
            latitude=coordinates[1],
            longitude=coordinates[0],
            place_id=properties.get("mapbox_id"),
            name=properties.get("name"),
            address_line_1=properties.get("address"),
            city=(context.get("place") or {}).get("name"),
            state=(context.get("region") or {}).get("name"),
            postal_code=(context.get("postcode") or {}).get("name"),
            country=(context.get("country") or {}).get("name"),
            confidence=confidence,
        )

    def geocode_address(self, address: str) -> GeocodeResult:
        data = self._get(_GEOCODING_URL, {"q": address, "limit": 5})
        features = data.get("features", [])
        candidates = [self._feature_to_candidate(f, "unknown") for f in features]
        for candidate in candidates:
            score = _address_match_score(address, candidate.address_line_1 or candidate.formatted_address)
            candidate.confidence = "high" if score >= 0.75 else "medium" if score >= 0.4 else "low"
        return GeocodeResult(candidates=candidates, query=address, provider=self.name)

    def reverse_geocode(self, latitude: float, longitude: float) -> GeocodeResult:
        data = self._get(_REVERSE_GEOCODING_URL, {"longitude": longitude, "latitude": latitude})
        features = data.get("features", [])
        confidence = "high" if features else "unknown"
        candidates = [self._feature_to_candidate(f, confidence) for f in features]
        return GeocodeResult(
            candidates=candidates, query=f"{latitude},{longitude}", provider=self.name
        )

    def search_business(
        self, query: str, *, near: tuple[float, float] | None = None
    ) -> GeocodeResult:
        session_token = str(uuid.uuid4())
        params: dict = {"q": query, "session_token": session_token, "limit": 5}
        if near is not None:
            params["proximity"] = f"{near[1]},{near[0]}"  # lng,lat

        data = self._get(_SEARCHBOX_SUGGEST_URL, params)
        suggestions = data.get("suggestions", [])

        candidates: list[LocationCandidate] = []
        seen_place_ids: set[str] = set()
        for suggestion in suggestions:
            mapbox_id = suggestion.get("mapbox_id")
            if not mapbox_id or mapbox_id in seen_place_ids:
                continue
            seen_place_ids.add(mapbox_id)
            candidate = self._retrieve_suggestion(mapbox_id, session_token)
            if candidate is None:
                continue
            # The Suggest API returning many text completions for an
            # under-specific query says nothing about whether the best
            # candidate is a strong match — score each one against the
            # address text actually searched for instead of just counting
            # how many suggestions came back.
            score = _address_match_score(query, candidate.address_line_1 or candidate.formatted_address)
            candidate.confidence = "high" if score >= 0.75 else "medium" if score >= 0.4 else "low"
            candidates.append(candidate)

        return GeocodeResult(candidates=candidates, query=query, provider=self.name)

    def _retrieve_suggestion(self, mapbox_id: str, session_token: str) -> LocationCandidate | None:
        url = f"{_SEARCHBOX_RETRIEVE_URL}/{mapbox_id}"
        data = self._get(url, {"session_token": session_token})
        features = data.get("features", [])
        if not features:
            return None
        return self._feature_to_candidate(features[0], confidence="high")

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
        profile = _MODE_PROFILE.get(mode, "driving")

        # Mapbox's Matrix API takes ONE coordinate list embedded in the URL
        # path itself (not a query param), plus source/destination indices
        # into that same list — it does not accept two separate lists.
        # De-duplicate origins/destinations into a single point list so
        # overlapping calls (e.g. calculate_travel_time_matrix(points, points),
        # as route generation always does) don't double up coordinates and
        # needlessly approach Mapbox's per-request coordinate cap.
        unique_points: list[tuple[float, float]] = []
        point_index: dict[tuple[float, float], int] = {}
        for point in origins + destinations:
            if point not in point_index:
                point_index[point] = len(unique_points)
                unique_points.append(point)

        coordinates = ";".join(f"{lng},{lat}" for lat, lng in unique_points)
        sources = ";".join(str(point_index[p]) for p in origins)
        destinations_idx = ";".join(str(point_index[p]) for p in destinations)

        url = f"https://api.mapbox.com/directions-matrix/v1/mapbox/{profile}/{coordinates}"
        data = self._get(
            url,
            {
                "sources": sources,
                "destinations": destinations_idx,
                "annotations": "duration,distance",
            },
        )
        if data.get("code") != "Ok":
            raise LocationProviderError(f"Mapbox Matrix error: {data.get('code')}")

        durations = data.get("durations", [])
        distances = data.get("distances", [])

        matrix: list[list[TravelTimeResult | None]] = []
        for i, origin in enumerate(origins):
            row_results: list[TravelTimeResult | None] = []
            for j, destination in enumerate(destinations):
                duration = durations[i][j] if i < len(durations) and j < len(durations[i]) else None
                distance = distances[i][j] if i < len(distances) and j < len(distances[i]) else None
                if duration is None or distance is None:
                    row_results.append(None)
                    continue
                row_results.append(
                    TravelTimeResult(
                        duration_seconds=int(duration),
                        distance_meters=float(distance),
                        origin=origin,
                        destination=destination,
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
        # Google Maps deep links work universally (installed on nearly every
        # phone) and are far more broadly supported as an external navigation
        # target than Mapbox's own consumer apps, so we still hand off
        # navigation to Google Maps regardless of which provider is used for
        # geocoding/search/distance. This is just a URL scheme, not an API call.
        def fmt(value: tuple[float, float] | str) -> str:
            if isinstance(value, tuple):
                return f"{value[0]},{value[1]}"
            return value

        params = {"api": "1", "destination": fmt(destination)}
        if origin is not None:
            params["origin"] = fmt(origin)
        return f"https://www.google.com/maps/dir/?{urllib.parse.urlencode(params)}"
