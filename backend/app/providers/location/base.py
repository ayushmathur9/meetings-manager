"""Provider-agnostic location abstraction.

Every map/geocoding call in the backend goes through this interface, never
directly through a vendor SDK. This keeps Google Maps (or any future provider,
e.g. Mapbox) swappable without touching business logic in the services layer.

None of these methods ever fabricate a result: if a provider finds nothing or
is ambiguous, callers get an empty list / None rather than a guessed value.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LocationCandidate:
    """A single real-world place a provider found for a search/geocode query."""

    formatted_address: str
    latitude: float
    longitude: float
    place_id: str | None
    name: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    confidence: str = "unknown"  # "high" | "medium" | "low" | "unknown"


@dataclass
class GeocodeResult:
    candidates: list[LocationCandidate]
    query: str
    provider: str


@dataclass
class DistanceResult:
    distance_meters: float
    origin: tuple[float, float]
    destination: tuple[float, float]


@dataclass
class TravelTimeResult:
    duration_seconds: int
    distance_meters: float
    origin: tuple[float, float]
    destination: tuple[float, float]
    mode: str = "driving"


class LocationProviderError(RuntimeError):
    """Raised when the underlying provider returns an unexpected/error status."""


class LocationProvider(ABC):
    """Abstract interface for geocoding, business lookup, distance, and navigation."""

    name: str

    @abstractmethod
    def search_business(
        self, query: str, *, near: tuple[float, float] | None = None
    ) -> GeocodeResult:
        """Search for a real-world business by name (+ optional address/city context).

        Used during import location verification to find the actual business
        location rather than just geocoding a possibly-stale address string.
        Returns zero, one, or multiple candidates — callers must not silently
        pick a candidate when there is more than one plausible match.
        """
        raise NotImplementedError

    @abstractmethod
    def geocode_address(self, address: str) -> GeocodeResult:
        """Convert a free-text address into coordinates + a normalized address."""
        raise NotImplementedError

    @abstractmethod
    def reverse_geocode(self, latitude: float, longitude: float) -> GeocodeResult:
        """Convert coordinates into a human-readable address."""
        raise NotImplementedError

    @abstractmethod
    def calculate_distance(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> DistanceResult:
        """Straight-line-independent distance between two points (provider-computed)."""
        raise NotImplementedError

    @abstractmethod
    def calculate_travel_time(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        mode: str = "driving",
    ) -> TravelTimeResult:
        """Estimated real-world travel time/distance between two points."""
        raise NotImplementedError

    @abstractmethod
    def calculate_travel_time_matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
        *,
        mode: str = "driving",
    ) -> list[list[TravelTimeResult | None]]:
        """Batched pairwise travel times, used by route generation to avoid N^2 calls."""
        raise NotImplementedError

    @abstractmethod
    def create_navigation_link(
        self,
        destination: tuple[float, float] | str,
        *,
        origin: tuple[float, float] | str | None = None,
    ) -> str:
        """Build an external navigation deep link (e.g. Google Maps directions URL)."""
        raise NotImplementedError
