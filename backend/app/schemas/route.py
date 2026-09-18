import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict

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
    meeting_id: uuid.UUID
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
