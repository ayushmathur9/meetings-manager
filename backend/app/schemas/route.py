import datetime as dt
import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.company import CompanyStatus
from app.models.route import RouteStatus


class NamedLocation(BaseModel):
    name: str
    address: str | None = None
    latitude: float
    longitude: float


class GenerateRouteRequest(BaseModel):
    salesperson_id: uuid.UUID
    date: date
    start_location: NamedLocation
    end_location: NamedLocation | None = None
    working_hours_start: time = time(9, 0)
    working_hours_end: time = time(17, 0)
    meeting_duration_minutes: int = 25
    travel_buffer_minutes: int = 10
    meeting_ids: list[uuid.UUID]


class PlanDayRequest(BaseModel):
    salesperson_id: uuid.UUID
    date: date
    start_location: NamedLocation
    end_location: NamedLocation | None = None
    working_hours_start: time = time(9, 0)
    working_hours_end: time = time(17, 0)
    meeting_duration_minutes: int = 25
    travel_buffer_minutes: int = 10
    target_meetings: int = 6
    radius_miles: float = 25
    industry: str | None = None
    status: CompanyStatus | None = None
    include_unverified: bool = False


class RouteStopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID | None
    sequence: int
    arrival_time: time | None
    departure_time: time | None
    travel_time_seconds: int | None
    distance_meters: float | None
    company_name: str
    company_id: uuid.UUID
    address_line_1: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    meeting_status: str
    contact_name: str | None = None


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    salesperson_id: uuid.UUID
    date: date
    start_location: dict
    end_location: dict | None
    status: RouteStatus
    estimated_distance_meters: float | None
    estimated_duration_seconds: int | None
    stops: list[RouteStopOut]


class ReorderRouteRequest(BaseModel):
    ordered_meeting_ids: list[uuid.UUID]


class PlanDaySummary(BaseModel):
    eligible_count: int
    verified_count: int
    in_territory_count: int
    scheduled_count: int
    excluded_unverified_count: int
    fixed_meeting_count: int
    working_hours_end: time
    last_stop_departure: time | None
    fits_within_working_hours: bool
    available_seconds: int


class PlanDayResult(BaseModel):
    route: RouteOut
    summary: PlanDaySummary


# ---------------------------------------------------------------------------
# Sales-day route planner (Geoapify-backed)
# ---------------------------------------------------------------------------

EndMode = Literal["same_as_start", "custom", "none"]
Priority = Literal["high", "medium", "low"]
RadiusStatus = Literal["inside", "outside", "missing_coordinates"]

MEETING_DURATION_OPTIONS = (15, 20, 25, 30, 45, 60)


class RoutePlanConfig(BaseModel):
    """Everything about a sales day except which prospects are on it."""

    salesperson_id: uuid.UUID | None = None  # defaults to the current user
    date: dt.date
    name: str | None = Field(default=None, max_length=255)
    start_location: NamedLocation
    # The UI no longer offers an end location (the day ends at the last
    # meeting); other modes remain only so older saved routes still load.
    end_mode: EndMode = "none"
    end_location: NamedLocation | None = None
    working_hours_start: time = time(8, 30)
    working_hours_end: time = time(16, 30)
    meeting_duration_minutes: int = Field(default=25, ge=5, le=480)
    travel_buffer_minutes: int = Field(default=0, ge=0, le=120)
    radius_miles: float = Field(default=20, gt=0, le=250)
    allow_overtime: bool = False

    @model_validator(mode="after")
    def _check(self) -> "RoutePlanConfig":
        if self.working_hours_end <= self.working_hours_start:
            raise ValueError("Working hours must end after they start")
        if self.end_mode == "custom" and self.end_location is None:
            raise ValueError("Choose an end location, or set the end to 'Same as start' / 'No fixed end'")
        return self

    def resolved_end(self) -> NamedLocation | None:
        if self.end_mode == "same_as_start":
            return self.start_location
        if self.end_mode == "custom":
            return self.end_location
        return None


class CandidatesRequest(BaseModel):
    salesperson_id: uuid.UUID | None = None
    date: dt.date | None = None
    start_location: NamedLocation
    radius_miles: float = Field(default=20, gt=0, le=250)
    search: str | None = None
    # "all" (admin only) lists every company, not just the salesperson's prospects.
    scope: Literal["assigned", "all"] = "assigned"


class RouteCandidate(BaseModel):
    company_id: uuid.UUID
    company_name: str
    industry: str | None = None
    status: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    verification_status: str | None = None
    priority: Priority = "medium"
    distance_miles: float | None = None
    radius_status: RadiusStatus
    contact_name: str | None = None
    phone: str | None = None
    assigned_user_id: uuid.UUID | None = None
    existing_meeting_id: uuid.UUID | None = None
    existing_meeting_time: time | None = None
    existing_meeting_fixed: bool = False


class CandidatesOut(BaseModel):
    radius_miles: float
    inside_count: int
    outside_count: int
    missing_count: int
    candidates: list[RouteCandidate]


class PlannerStopInput(BaseModel):
    company_id: uuid.UUID
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    priority: Priority | None = None


class OptimizeRouteRequest(RoutePlanConfig):
    stops: list[PlannerStopInput] = Field(min_length=1)
    # False = keep the given order (manual reorder) and only recalculate times.
    optimize: bool = True


class PlannedStop(BaseModel):
    sequence: int
    company_id: uuid.UUID
    location_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    meeting_status: str | None = None
    company_name: str
    address: str | None = None
    latitude: float | None = None  # only None for stops of legacy routes
    longitude: float | None = None
    priority: Priority = "medium"
    contact_name: str | None = None
    phone: str | None = None
    duration_minutes: int
    travel_time_seconds: int
    distance_meters: float
    arrival_time: time
    meeting_start: time
    meeting_end: time
    departure_time: time
    wait_seconds: int = 0
    late_seconds: int = 0
    is_fixed_time: bool = False
    outside_hours: bool = False
    outside_radius: bool = False
    location_changed: bool = False


class UnscheduledStopOut(BaseModel):
    company_id: uuid.UUID
    company_name: str
    priority: Priority = "medium"
    reason: Literal["does_not_fit", "unreachable", "missing_coordinates", "outside_radius"]
    message: str


class RoutePlanOut(BaseModel):
    config: RoutePlanConfig
    stops: list[PlannedStop]
    unscheduled: list[UnscheduledStopOut] = []
    warnings: list[str] = []
    selected_count: int
    scheduled_count: int
    day_start: time
    day_finish: time
    return_travel_seconds: int = 0
    return_distance_meters: float = 0
    total_distance_meters: float
    total_driving_seconds: int
    total_meeting_seconds: int
    total_wait_seconds: int = 0
    total_duration_seconds: int
    geometry: list | None = None  # GeoJSON MultiLineString coordinates ([lng, lat])
    routing_engine: str  # who supplied road travel times ("geoapify", "mapbox", ...)
    optimization_engine: str  # "geoapify_route_planner" | "local" | "manual"


class SavedRouteOut(RoutePlanOut):
    id: uuid.UUID
    status: RouteStatus
    salesperson_name: str | None = None
    created_at: datetime
    updated_at: datetime
    is_stale: bool = False


class RouteListItem(BaseModel):
    id: uuid.UUID
    name: str | None
    date: dt.date
    salesperson_id: uuid.UUID
    salesperson_name: str | None
    status: RouteStatus
    stop_count: int
    start_name: str | None
    total_distance_meters: float | None
    total_driving_seconds: int | None
    total_duration_seconds: int | None
    updated_at: datetime


class SaveRouteRequest(BaseModel):
    plan: RoutePlanOut
    status: RouteStatus | None = None


class UpdateRouteRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    status: RouteStatus | None = None
    plan: RoutePlanOut | None = None


class RecalculateRouteRequest(BaseModel):
    optimize: bool = False


class GeocodeMissingRequest(BaseModel):
    company_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class GeocodeMissingResult(BaseModel):
    company_id: uuid.UUID
    company_name: str
    status: Literal["verified", "already_verified", "needs_review", "failed"]
    latitude: float | None = None
    longitude: float | None = None
    message: str | None = None
