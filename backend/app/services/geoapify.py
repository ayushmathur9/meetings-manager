"""Geoapify integration — the ONLY module that talks to Geoapify over HTTP.

Geoapify is our geospatial engine: geocoding, road-network routes, travel-time
matrices and (optionally) stop-order optimization via the Route Planner API.
Everything business-related (who can see what, priorities, meeting durations,
working hours, persistence) stays in the application — this module only
translates between our types and Geoapify's wire format.

Conventions:
  * Coordinates in/out of this module are ``(latitude, longitude)`` tuples,
    matching the rest of the backend. Geoapify itself mixes ``lat,lon`` (GET
    query strings) and ``[lon, lat]`` (JSON bodies) — that conversion happens
    here and nowhere else.
  * The API key is read from ``GEOAPIFY_API_KEY`` and is never logged, never
    returned to callers and never included in exception messages.
  * Every failure is raised as a ``GeoapifyError`` subclass carrying a
    ``user_message`` that is safe to show to end users; raw Geoapify error
    bodies are logged server-side only.

Docs: https://apidocs.geoapify.com/docs/routing/
      https://apidocs.geoapify.com/docs/route-matrix/
      https://apidocs.geoapify.com/docs/route-planner/
      https://apidocs.geoapify.com/docs/geocoding/
"""

from __future__ import annotations

import json as json_module
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.providers.location.base import LocationCandidate, LocationProviderError, TravelTimeResult

logger = logging.getLogger("app.geoapify")

BASE_URL = "https://api.geoapify.com"
_GEOCODE_SEARCH_PATH = "/v1/geocode/search"
_GEOCODE_REVERSE_PATH = "/v1/geocode/reverse"
_ROUTING_PATH = "/v1/routing"
_ROUTE_MATRIX_PATH = "/v1/routematrix"
_ROUTE_PLANNER_PATH = "/v1/routeplanner"

MATRIX_MAX_CELLS = 1000  # Geoapify limit: sources x targets per request
ROUTING_MAX_WAYPOINTS = 50

_MODE_ALIASES = {"driving": "drive", "drive": "drive", "walking": "walk", "walk": "walk",
                 "bicycling": "bicycle", "bicycle": "bicycle", "truck": "truck"}

Coordinate = tuple[float, float]  # (latitude, longitude)


# --------------------------------------------------------------------------- errors


class GeoapifyError(LocationProviderError):
    """Base class. ``user_message`` is safe to show to end users."""

    code = "geoapify_error"
    user_message = "The routing service returned an unexpected error. Please try again."

    def __init__(self, detail: str = "", *, user_message: str | None = None) -> None:
        super().__init__(detail or self.user_message)
        if user_message:
            self.user_message = user_message


class GeoapifyNotConfiguredError(GeoapifyError):
    code = "routing_not_configured"
    user_message = (
        "Route optimization is not configured. An administrator needs to set GEOAPIFY_API_KEY "
        "on the backend."
    )


class GeoapifyAuthError(GeoapifyError):
    code = "routing_auth_failed"
    user_message = (
        "The routing service rejected our credentials. An administrator needs to check the "
        "Geoapify API key."
    )


class GeoapifyRateLimitError(GeoapifyError):
    code = "routing_rate_limited"
    user_message = "The routing service is receiving too many requests right now. Please wait a minute and try again."


class GeoapifyUnavailableError(GeoapifyError):
    code = "routing_unavailable"
    user_message = "The routing service is unavailable right now. Please try again shortly."


class GeoapifyBadRequestError(GeoapifyError):
    code = "routing_bad_request"
    user_message = "The routing service could not process this request. Check the selected locations."


class GeoapifyNoRouteError(GeoapifyError):
    code = "no_route_found"
    user_message = "No drivable route could be found between the selected locations."


class InvalidCoordinatesError(ValueError):
    """Raised before any request is made when a coordinate is unusable."""


# --------------------------------------------------------------------------- results


@dataclass
class RouteLeg:
    distance_meters: float
    duration_seconds: int


@dataclass
class RouteResult:
    distance_meters: float
    duration_seconds: int
    legs: list[RouteLeg]
    # One [lng, lat] polyline per leg (GeoJSON MultiLineString coordinates).
    geometry: list[list[list[float]]]


@dataclass
class PlannerJob:
    id: str
    location: Coordinate
    duration_seconds: int
    priority: int = 0  # 0-100, Geoapify semantics (higher = more important)


@dataclass
class PlannerResult:
    order: list[int]  # indices into the submitted job list, in visiting order
    unassigned: list[int] = field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def validate_coordinate(point: Coordinate, *, label: str = "location") -> Coordinate:
    try:
        lat, lng = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        raise InvalidCoordinatesError(f"{label} has no usable coordinates")
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise InvalidCoordinatesError(f"{label} has non-numeric coordinates")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise InvalidCoordinatesError(f"{label} has out-of-range coordinates ({lat}, {lng})")
    if abs(lat) < 1e-9 and abs(lng) < 1e-9:
        raise InvalidCoordinatesError(f"{label} has placeholder (0, 0) coordinates")
    return (lat, lng)


# Geoapify rank.match_type values meaning the house number/building itself
# wasn't matched — the point is only somewhere on the street, in the ZIP or in
# the city. ("disrict" is Geoapify's own spelling.)
_COARSE_MATCH_TYPES = {
    "match_by_street",
    "match_by_postcode",
    "match_by_city_or_disrict",
    "match_by_city_or_district",
    "match_by_country_or_state",
}
_HOUSE_NUMBER = re.compile(r"^\s*(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s+(.+)$")


def split_house_number(street: str | None) -> tuple[str | None, str | None]:
    """"123 Main St" -> ("123", "Main St"). Streets without a leading number
    (e.g. "One Market Plaza") come back unchanged with no house number."""
    if not street:
        return None, None
    match = _HOUSE_NUMBER.match(street)
    if not match:
        return None, street.strip()
    return match.group(1), match.group(2).strip()


def _classify_confidence(result: dict) -> str:
    """Map a Geoapify result to our high/medium/low scale.

    "high" (the only level ever auto-accepted) requires a match resolved to
    an actual building/place — a confident match on just a street or city is
    not good enough to drive to. ``confidence_building_level`` is preferred
    over the overall score when present: a "<company name> <address>" query
    lowers the overall score for the unmatched name words even when the
    building itself matched exactly.
    """
    rank = result.get("rank") or {}
    score = float(rank.get("confidence") or 0)
    building_score = rank.get("confidence_building_level")
    if building_score is not None:
        score = max(score, float(building_score))
    result_type = result.get("result_type")
    coarse = rank.get("match_type") in _COARSE_MATCH_TYPES

    if score >= 0.9 and result_type in {"building", "amenity"} and not coarse:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _round(point: Coordinate) -> Coordinate:
    return (round(point[0], 6), round(point[1], 6))


def _mode(mode: str) -> str:
    return _MODE_ALIASES.get(mode, "drive")


class _TTLCache:
    """Tiny thread-safe LRU cache with per-entry expiry (process-local)."""

    def __init__(self, max_entries: int = 512) -> None:
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_entries

    def get(self, key: Any) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: Any, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl_seconds, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# --------------------------------------------------------------------------- client


class GeoapifyClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float | None = None,
        cache_ttl_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.geoapify_api_key).strip()
        self._timeout = timeout or settings.geoapify_timeout_seconds
        self._cache_ttl = (
            cache_ttl_seconds if cache_ttl_seconds is not None else settings.geoapify_cache_ttl_seconds
        )
        self._transport = transport
        self._cache = _TTLCache()

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key) and self._api_key not in {"your_geoapify_api_key", "REPLACE_WITH_REAL_KEY"}

    # ---------------------------------------------------------------- transport

    def _request(
        self, method: str, path: str, *, params: dict | None = None, json: dict | None = None
    ) -> Any:
        if not self.is_configured:
            raise GeoapifyNotConfiguredError("GEOAPIFY_API_KEY is not set")

        # Every call we make is idempotent, so a transient failure (timeout,
        # network blip, 5xx) is retried once before giving up.
        for attempt in (1, 2):
            try:
                response = self._send(method, path, params=params, json=json)
            except GeoapifyUnavailableError:
                if attempt == 2:
                    raise
                time.sleep(0.5)
                continue
            if response.status_code >= 500 and attempt == 1:
                logger.warning("Geoapify %s %s returned %s, retrying", method, path, response.status_code)
                time.sleep(0.5)
                continue
            break
        return self._handle_response(method, path, response)

    def _send(self, method: str, path: str, *, params: dict | None, json: dict | None) -> httpx.Response:
        query = {**(params or {}), "apiKey": self._api_key}
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.request(method, f"{BASE_URL}{path}", params=query, json=json)
        except httpx.TimeoutException:
            logger.warning("Geoapify %s %s timed out after %.1fs", method, path, self._timeout)
            raise GeoapifyUnavailableError(f"{path} timed out")
        except httpx.HTTPError as exc:
            # str(exc) can include the request URL (and therefore the key) — log the type only.
            logger.warning("Geoapify %s %s network error: %s", method, path, type(exc).__name__)
            raise GeoapifyUnavailableError(f"{path} network error: {type(exc).__name__}")
        logger.info(
            "Geoapify %s %s -> %s (%.0f ms)", method, path, response.status_code, (time.monotonic() - started) * 1000
        )
        return response

    def _handle_response(self, method: str, path: str, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            message = self._error_message(response)
            logger.warning("Geoapify %s %s failed [%s]: %s", method, path, response.status_code, message)
            if response.status_code in (401, 403):
                raise GeoapifyAuthError(message)
            if response.status_code == 429:
                raise GeoapifyRateLimitError(message)
            if response.status_code >= 500:
                raise GeoapifyUnavailableError(message)
            if "route" in message.lower() and ("not found" in message.lower() or "no path" in message.lower()):
                raise GeoapifyNoRouteError(message)
            raise GeoapifyBadRequestError(message)

        try:
            return response.json()
        except ValueError:
            logger.warning("Geoapify %s %s returned non-JSON body", method, path)
            raise GeoapifyUnavailableError(f"{path} returned an invalid response")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:300]
        if isinstance(body, dict):
            return str(body.get("message") or body.get("error") or body)[:300]
        return str(body)[:300]

    # ---------------------------------------------------------------- geocoding

    def geocode_address(self, address: str, *, country_code: str | None = "us", limit: int = 5) -> list[LocationCandidate]:
        text = (address or "").strip()
        if len(text) < 3:
            raise GeoapifyBadRequestError("address too short", user_message="The address is incomplete.")
        cache_key = ("geocode", text.lower(), country_code, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, Any] = {"text": text, "format": "json", "limit": limit}
        if country_code:
            params["filter"] = f"countrycode:{country_code}"
        data = self._request("GET", _GEOCODE_SEARCH_PATH, params=params)
        candidates = self._parse_geocode_results(data)
        self._cache.set(cache_key, candidates, self._cache_ttl)
        return candidates

    def geocode_structured(
        self,
        *,
        street: str | None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country_code: str | None = "us",
        limit: int = 5,
    ) -> list[LocationCandidate]:
        """Geocode with each address part in its own field, so Geoapify never
        has to guess which words are the street and which are the city."""
        housenumber, street_name = split_house_number(street)
        params: dict[str, Any] = {
            "housenumber": housenumber,
            "street": street_name,
            "city": city,
            "state": state,
            "postcode": postal_code,
        }
        params = {k: v.strip() for k, v in params.items() if v and v.strip()}
        if not params.get("street") and not params.get("postcode") and not params.get("city"):
            raise GeoapifyBadRequestError("address too short", user_message="The address is incomplete.")
        cache_key = ("geocode_structured", tuple(sorted((k, v.lower()) for k, v in params.items())), country_code, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params.update({"format": "json", "limit": limit})
        if country_code:
            params["filter"] = f"countrycode:{country_code}"
        data = self._request("GET", _GEOCODE_SEARCH_PATH, params=params)
        candidates = self._parse_geocode_results(data)
        self._cache.set(cache_key, candidates, self._cache_ttl)
        return candidates

    def reverse_geocode(self, latitude: float, longitude: float) -> list[LocationCandidate]:
        lat, lng = validate_coordinate((latitude, longitude))
        cache_key = ("reverse", _round((lat, lng)))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        data = self._request("GET", _GEOCODE_REVERSE_PATH, params={"lat": lat, "lon": lng, "format": "json"})
        candidates = self._parse_geocode_results(data)
        self._cache.set(cache_key, candidates, self._cache_ttl)
        return candidates

    @staticmethod
    def _parse_geocode_results(data: Any) -> list[LocationCandidate]:
        if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
            raise GeoapifyUnavailableError("geocode response missing 'results'")
        candidates: list[LocationCandidate] = []
        seen: set[str] = set()
        for result in data.get("results", []):
            try:
                lat, lng = validate_coordinate((result["lat"], result["lon"]))
            except (KeyError, InvalidCoordinatesError):
                continue
            place_id = result.get("place_id")
            if place_id and place_id in seen:
                continue
            if place_id:
                seen.add(place_id)
            confidence = _classify_confidence(result)
            street = " ".join(p for p in [result.get("housenumber"), result.get("street")] if p) or None
            candidates.append(
                LocationCandidate(
                    formatted_address=result.get("formatted") or "",
                    latitude=lat,
                    longitude=lng,
                    place_id=place_id,
                    name=result.get("name"),
                    address_line_1=street or result.get("address_line1"),
                    city=result.get("city"),
                    state=result.get("state"),
                    postal_code=result.get("postcode"),
                    country=result.get("country"),
                    confidence=confidence,
                )
            )
        return candidates

    # ---------------------------------------------------------------- routing

    def get_route(self, waypoints: list[Coordinate], *, mode: str = "drive") -> RouteResult:
        if len(waypoints) < 2:
            raise GeoapifyBadRequestError("routing needs at least two waypoints")
        if len(waypoints) > ROUTING_MAX_WAYPOINTS:
            raise GeoapifyBadRequestError(
                "too many waypoints", user_message=f"A route can have at most {ROUTING_MAX_WAYPOINTS} stops."
            )
        points = [_round(validate_coordinate(p, label=f"Waypoint {i + 1}")) for i, p in enumerate(waypoints)]
        cache_key = ("route", _mode(mode), tuple(points))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._request(
            "GET",
            _ROUTING_PATH,
            params={"waypoints": "|".join(f"{lat},{lng}" for lat, lng in points), "mode": _mode(mode)},
        )
        features = data.get("features") if isinstance(data, dict) else None
        if not features:
            raise GeoapifyNoRouteError("routing response had no features")
        feature = features[0]
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if geometry.get("type") == "LineString":
            coords = [coords]
        legs = [
            RouteLeg(distance_meters=float(leg.get("distance") or 0), duration_seconds=int(round(leg.get("time") or 0)))
            for leg in props.get("legs") or []
        ]
        if props.get("distance") is None or props.get("time") is None:
            raise GeoapifyUnavailableError("routing response missing distance/time")
        result = RouteResult(
            distance_meters=float(props["distance"]),
            duration_seconds=int(round(props["time"])),
            legs=legs,
            geometry=coords,
        )
        self._cache.set(cache_key, result, self._cache_ttl)
        return result

    def get_route_matrix(
        self, sources: list[Coordinate], targets: list[Coordinate], *, mode: str = "drive"
    ) -> list[list[TravelTimeResult | None]]:
        """Travel time/distance for every source→target pair. ``None`` marks an
        unreachable pair. Identical coordinates are de-duplicated before the
        request and results are cached by the exact (rounded) point set."""
        src = [_round(validate_coordinate(p, label=f"Source {i + 1}")) for i, p in enumerate(sources)]
        dst = [_round(validate_coordinate(p, label=f"Target {i + 1}")) for i, p in enumerate(targets)]
        if not src or not dst:
            return [[] for _ in src]

        unique_src = list(dict.fromkeys(src))
        unique_dst = list(dict.fromkeys(dst))
        if len(unique_src) * len(unique_dst) > MATRIX_MAX_CELLS:
            raise GeoapifyBadRequestError(
                "matrix too large", user_message="Too many stops selected to calculate travel times in one request."
            )

        cache_key = ("matrix", _mode(mode), tuple(unique_src), tuple(unique_dst))
        cells = self._cache.get(cache_key)
        if cells is None:
            data = self._request(
                "POST",
                _ROUTE_MATRIX_PATH,
                json={
                    "mode": _mode(mode),
                    "sources": [{"location": [lng, lat]} for lat, lng in unique_src],
                    "targets": [{"location": [lng, lat]} for lat, lng in unique_dst],
                },
            )
            rows = data.get("sources_to_targets") if isinstance(data, dict) else None
            if not isinstance(rows, list) or len(rows) != len(unique_src):
                raise GeoapifyUnavailableError("matrix response malformed")
            cells = {}
            for row in rows:
                for cell in row or []:
                    if not isinstance(cell, dict):
                        continue
                    i, j = cell.get("source_index"), cell.get("target_index")
                    if i is None or j is None:
                        continue
                    t, d = cell.get("time"), cell.get("distance")
                    cells[(i, j)] = None if t is None or d is None else (int(round(t)), float(d))
            self._cache.set(cache_key, cells, self._cache_ttl)

        src_index = {p: i for i, p in enumerate(unique_src)}
        dst_index = {p: j for j, p in enumerate(unique_dst)}
        matrix: list[list[TravelTimeResult | None]] = []
        for o in src:
            row: list[TravelTimeResult | None] = []
            for d in dst:
                if o == d:
                    row.append(TravelTimeResult(0, 0.0, o, d, mode))
                    continue
                value = cells.get((src_index[o], dst_index[d]))
                row.append(None if value is None else TravelTimeResult(value[0], value[1], o, d, mode))
            matrix.append(row)
        return matrix

    def optimize_route(
        self,
        start: Coordinate,
        jobs: list[PlannerJob],
        *,
        end: Coordinate | None = None,
        available_seconds: int | None = None,
        mode: str = "drive",
    ) -> PlannerResult:
        """Ask Geoapify's Route Planner for a visiting order. Start (and end,
        if given) are fixed; only the jobs are reordered. Jobs that don't fit
        the time window come back in ``unassigned``."""
        if not jobs:
            return PlannerResult(order=[])
        agent: dict[str, Any] = {"start_location": self._lonlat(start, "Start location")}
        if end is not None:
            agent["end_location"] = self._lonlat(end, "End location")
        if available_seconds is not None:
            agent["time_windows"] = [[0, max(int(available_seconds), 0)]]
        body = {
            "mode": _mode(mode),
            "agents": [agent],
            "jobs": [
                {
                    "id": job.id,
                    "location": self._lonlat(job.location, f"Stop {job.id}"),
                    "duration": max(int(job.duration_seconds), 0),
                    "priority": max(0, min(100, int(job.priority))),
                }
                for job in jobs
            ],
        }
        cache_key = ("planner", json_module.dumps(body, sort_keys=True))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._request("POST", _ROUTE_PLANNER_PATH, json=body)
        if not isinstance(data, dict):
            raise GeoapifyUnavailableError("route planner response malformed")

        order: list[int] = []
        for feature in data.get("features") or []:
            for action in (feature.get("properties") or {}).get("actions") or []:
                job_index = action.get("job_index")
                if job_index is not None and action.get("type") not in ("start", "end") and job_index not in order:
                    order.append(int(job_index))
        issues = (data.get("properties") or {}).get("issues") or {}
        unassigned = list(issues.get("unassigned_jobs") or issues.get("unassignedJobs") or [])
        missing = [i for i in range(len(jobs)) if i not in order and i not in unassigned]
        result = PlannerResult(order=[i for i in order if 0 <= i < len(jobs)], unassigned=unassigned + missing)
        self._cache.set(cache_key, result, self._cache_ttl)
        return result

    @staticmethod
    def _lonlat(point: Coordinate, label: str) -> list[float]:
        lat, lng = validate_coordinate(point, label=label)
        return [lng, lat]

    def clear_cache(self) -> None:
        self._cache.clear()


_default_client: GeoapifyClient | None = None
_default_lock = threading.Lock()


def get_geoapify_client() -> GeoapifyClient:
    """Process-wide client so the in-memory cache is shared across requests."""
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = GeoapifyClient()
        return _default_client


# Module-level convenience functions (the public surface described in the docs).


def geocode_address(address: str, **kwargs: Any) -> list[LocationCandidate]:
    return get_geoapify_client().geocode_address(address, **kwargs)


def reverse_geocode(latitude: float, longitude: float) -> list[LocationCandidate]:
    return get_geoapify_client().reverse_geocode(latitude, longitude)


def get_route(waypoints: list[Coordinate], **kwargs: Any) -> RouteResult:
    return get_geoapify_client().get_route(waypoints, **kwargs)


def get_route_matrix(sources: list[Coordinate], targets: list[Coordinate], **kwargs: Any):
    return get_geoapify_client().get_route_matrix(sources, targets, **kwargs)


def optimize_route(start: Coordinate, jobs: list[PlannerJob], **kwargs: Any) -> PlannerResult:
    return get_geoapify_client().optimize_route(start, jobs, **kwargs)
