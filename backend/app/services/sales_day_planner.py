"""Sales Day / Meeting Route Planner.

Pipeline for one planning request:

  1. Authorization  — salespeople plan only their own day with their own
                      prospects; admins can plan for anyone.
  2. PostGIS        — candidate prospects are filtered by real geographic
                      distance (ST_DWithin on geography) BEFORE anything is
                      sent to Geoapify. Only the stops the user selected are
                      ever sent out.
  3. Geoapify       — one travel-time matrix for start + stops + end (cached),
                      optionally a Route Planner order suggestion, and one
                      Routing call for the final road geometry.
  4. App rules      — route_optimizer.plan_day applies working hours, meeting
                      durations, committed meeting times and priority.
  5. Persistence    — saving a plan stores the configuration, ordered stops,
                      times, geometry and totals, and keeps the salesperson's
                      meetings for that day in sync.

Geoapify is only the geospatial engine; all business decisions live here and
in route_optimizer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time, timedelta

from geoalchemy2 import Geography
from sqlalchemy import cast, func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.company import Company
from app.models.contact import Contact
from app.models.location import Location, VerificationStatus
from app.models.meeting import Meeting, MeetingStatus
from app.models.prospect import Prospect
from app.models.route import Route, RouteStatus, RouteStop
from app.models.user import User, UserRole
from app.providers.location import get_location_provider
from app.schemas.meeting import MeetingCreate
from app.schemas.route import (
    CandidatesOut,
    CandidatesRequest,
    GeocodeMissingResult,
    NamedLocation,
    OptimizeRouteRequest,
    PlannedStop,
    PlannerStopInput,
    RouteCandidate,
    RouteListItem,
    RoutePlanConfig,
    RoutePlanOut,
    SavedRouteOut,
    UnscheduledStopOut,
)
from app.services import route_optimizer as opt
from app.services.geoapify import (
    GeoapifyAuthError,
    GeoapifyClient,
    GeoapifyError,
    GeoapifyNotConfiguredError,
    InvalidCoordinatesError,
    PlannerJob,
    get_geoapify_client,
    validate_coordinate,
)
from app.services.location_service import LocationService
from app.services.meeting_service import MeetingService
from app.services.normalization import parse_combined_address

logger = logging.getLogger("app.route_planner")

METERS_PER_MILE = 1609.344
_INACTIVE_MEETING_STATUSES = (MeetingStatus.CANCELLED, MeetingStatus.NO_SHOW)
_GEOAPIFY_PRIORITY = {"high": 100, "medium": 50, "low": 10}
_LOCATION_CHANGE_TOLERANCE = 1e-4  # ~11 m


class PlannerError(Exception):
    """An application-level planning failure with a user-safe message."""

    def __init__(self, status_code: int, code: str, message: str, companies: list[dict] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.companies = companies or []

    def detail(self) -> dict:
        detail: dict = {"code": self.code, "message": self.message}
        if self.companies:
            detail["companies"] = self.companies
        return detail


@dataclass
class _CompanyRow:
    company_id: uuid.UUID
    company_name: str
    industry: str | None
    status: str | None
    phone: str | None
    location_id: uuid.UUID | None
    address: str | None
    latitude: float | None
    longitude: float | None
    verification_status: str | None
    priority: str
    assigned_user_id: uuid.UUID | None
    distance_meters: float | None
    within_radius: bool | None

    @property
    def has_valid_coordinates(self) -> bool:
        try:
            validate_coordinate((self.latitude, self.longitude))
            return True
        except InvalidCoordinatesError:
            return False


def _format_clock(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def _seconds_between(start: time, end: time) -> int:
    return int((datetime.combine(date_type.min, end) - datetime.combine(date_type.min, start)).total_seconds())


def _address(location: Location | None) -> str | None:
    if location is None:
        return None
    if location.formatted_address:
        return location.formatted_address
    parts = [location.address_line_1, location.city, location.state]
    text = ", ".join(p for p in parts if p)
    return text or None


class SalesDayPlanner:
    def __init__(self, db: Session, geoapify: GeoapifyClient | None = None) -> None:
        self.db = db
        self.geoapify = geoapify or get_geoapify_client()
        self.settings = get_settings()

    # ------------------------------------------------------------------ access

    def resolve_salesperson(self, requested_id: uuid.UUID | None, current_user: User) -> User:
        if current_user.role != UserRole.ADMIN:
            if requested_id is not None and requested_id != current_user.id:
                raise PlannerError(403, "forbidden", "You can only plan your own routes.")
            return current_user
        if requested_id is None or requested_id == current_user.id:
            return current_user
        user = self.db.get(User, requested_id)
        if user is None or not user.active:
            raise PlannerError(404, "salesperson_not_found", "That salesperson doesn't exist or is inactive.")
        return user

    def ensure_can_access(self, route: Route, current_user: User) -> None:
        if current_user.role != UserRole.ADMIN and route.salesperson_id != current_user.id:
            # 404, not 403, so salespeople can't probe for other people's route ids.
            raise PlannerError(404, "route_not_found", "Route not found")

    # ------------------------------------------------------------------ PostGIS

    def _company_rows(
        self,
        *,
        center: NamedLocation | None = None,
        radius_miles: float | None = None,
        company_ids: list[uuid.UUID] | None = None,
        assigned_to: uuid.UUID | None = None,
        search: str | None = None,
    ) -> list[_CompanyRow]:
        lat_lng_point = func.ST_SetSRID(func.ST_MakePoint(Location.longitude, Location.latitude), 4326)
        point = cast(func.coalesce(lat_lng_point, Location.geom), Geography)
        columns = [
            Company.id,
            Company.name,
            Company.industry,
            Company.status,
            Company.phone,
            Location.id,
            Location,
            Prospect.priority,
            Prospect.assigned_user_id,
        ]
        if center is not None and radius_miles is not None:
            center_point = cast(
                func.ST_SetSRID(func.ST_MakePoint(center.longitude, center.latitude), 4326), Geography
            )
            columns += [
                func.ST_Distance(point, center_point).label("distance"),
                func.ST_DWithin(point, center_point, radius_miles * METERS_PER_MILE).label("within"),
            ]
        query = (
            self.db.query(*columns)
            .select_from(Company)
            .outerjoin(Prospect, Prospect.company_id == Company.id)
            .outerjoin(Location, (Location.company_id == Company.id) & Location.is_primary.is_(True))
        )
        if company_ids is not None:
            query = query.filter(Company.id.in_(company_ids))
        else:
            # Deleted in Bigin: not offered as a new stop (explicit ids still work).
            query = query.filter(Company.crm_deleted_at.is_(None))
        if assigned_to is not None:
            query = query.filter(Prospect.assigned_user_id == assigned_to)
        if search:
            like = f"%{search.strip()}%"
            query = query.filter(
                or_(Company.name.ilike(like), Company.industry.ilike(like), Location.city.ilike(like))
            )

        rows = []
        for r in query.all():
            location: Location | None = r[6]
            priority = r[7].value if r[7] is not None else "medium"
            rows.append(
                _CompanyRow(
                    company_id=r[0],
                    company_name=r[1],
                    industry=r[2],
                    status=r[3].value if r[3] is not None else None,
                    phone=r[4],
                    location_id=r[5],
                    address=_address(location),
                    latitude=location.latitude if location else None,
                    longitude=location.longitude if location else None,
                    verification_status=location.verification_status.value if location else None,
                    priority=priority,
                    assigned_user_id=r[8],
                    distance_meters=float(r[9]) if len(r) > 9 and r[9] is not None else None,
                    within_radius=bool(r[10]) if len(r) > 10 and r[10] is not None else None,
                )
            )
        return rows

    def _first_contacts(self, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, Contact]:
        if not company_ids:
            return {}
        contacts = (
            self.db.query(Contact)
            .filter(Contact.company_id.in_(company_ids))
            .order_by(Contact.company_id, Contact.created_at)
            .all()
        )
        first: dict[uuid.UUID, Contact] = {}
        for contact in contacts:
            first.setdefault(contact.company_id, contact)
        return first

    def _day_meetings(self, salesperson_id: uuid.UUID, day: date_type) -> dict[uuid.UUID, Meeting]:
        meetings = (
            self.db.query(Meeting)
            .filter(
                Meeting.salesperson_id == salesperson_id,
                Meeting.date == day,
                Meeting.status.notin_(_INACTIVE_MEETING_STATUSES),
            )
            .order_by(Meeting.start_time)
            .all()
        )
        by_company: dict[uuid.UUID, Meeting] = {}
        for meeting in meetings:
            by_company.setdefault(meeting.company_id, meeting)
        return by_company

    def find_candidates(self, request: CandidatesRequest, current_user: User) -> CandidatesOut:
        salesperson = self.resolve_salesperson(request.salesperson_id, current_user)
        self._validate_point(request.start_location, "Start location")
        scope_all = request.scope == "all" and current_user.role == UserRole.ADMIN
        rows = self._company_rows(
            center=request.start_location,
            radius_miles=request.radius_miles,
            assigned_to=None if scope_all else salesperson.id,
            search=request.search,
        )
        contacts = self._first_contacts([r.company_id for r in rows])
        meetings = self._day_meetings(salesperson.id, request.date) if request.date else {}

        candidates = []
        for row in rows:
            if not row.has_valid_coordinates:
                radius_status = "missing_coordinates"
            elif row.within_radius:
                radius_status = "inside"
            else:
                radius_status = "outside"
            meeting = meetings.get(row.company_id)
            contact = contacts.get(row.company_id)
            candidates.append(
                RouteCandidate(
                    company_id=row.company_id,
                    company_name=row.company_name,
                    industry=row.industry,
                    status=row.status,
                    address=row.address,
                    latitude=row.latitude,
                    longitude=row.longitude,
                    verification_status=row.verification_status,
                    priority=row.priority,
                    distance_miles=round(row.distance_meters / METERS_PER_MILE, 2)
                    if row.distance_meters is not None and radius_status != "missing_coordinates"
                    else None,
                    radius_status=radius_status,
                    contact_name=contact.full_name if contact else None,
                    phone=row.phone,
                    assigned_user_id=row.assigned_user_id,
                    existing_meeting_id=meeting.id if meeting else None,
                    existing_meeting_time=meeting.start_time if meeting else None,
                    existing_meeting_fixed=bool(meeting and not meeting.is_planner_generated),
                )
            )

        order = {"inside": 0, "outside": 1, "missing_coordinates": 2}
        candidates.sort(key=lambda c: (order[c.radius_status], c.distance_miles or 0, c.company_name.lower()))
        return CandidatesOut(
            radius_miles=request.radius_miles,
            inside_count=sum(c.radius_status == "inside" for c in candidates),
            outside_count=sum(c.radius_status == "outside" for c in candidates),
            missing_count=sum(c.radius_status == "missing_coordinates" for c in candidates),
            candidates=candidates,
        )

    # ------------------------------------------------------------------ planning

    @staticmethod
    def _validate_point(location: NamedLocation, label: str) -> tuple[float, float]:
        try:
            return validate_coordinate((location.latitude, location.longitude), label=label)
        except InvalidCoordinatesError as exc:
            raise PlannerError(422, "invalid_coordinates", f"{exc}. Choose the location again.")

    def _travel_matrix(self, points: list[tuple[float, float]]) -> tuple[opt.Matrix, str, list[str]]:
        """Road-network travel matrix. Geoapify when configured; otherwise the
        configured map provider (e.g. Mapbox) — never straight-line guesses."""
        warnings: list[str] = []
        if self.geoapify.is_configured:
            raw = self.geoapify.get_route_matrix(points, points)
            engine = "geoapify"
        else:
            provider = get_location_provider()
            if provider.name == "fallback_estimate":
                raise GeoapifyNotConfiguredError("no road-network provider configured")
            raw = provider.calculate_travel_time_matrix(points, points)
            engine = provider.name
            warnings.append(
                f"Travel times come from {provider.name.title()} because Geoapify isn't configured "
                "(GEOAPIFY_API_KEY). Road geometry won't be shown."
            )
        matrix: opt.Matrix = [
            [None if cell is None else (int(cell.duration_seconds), float(cell.distance_meters)) for cell in row]
            for row in raw
        ]
        return matrix, engine, warnings

    def build_plan(self, request: OptimizeRouteRequest, current_user: User) -> RoutePlanOut:
        salesperson = self.resolve_salesperson(request.salesperson_id, current_user)
        config = RoutePlanConfig(**request.model_dump(exclude={"stops", "optimize"}))
        config.salesperson_id = salesperson.id
        warnings: list[str] = []

        # De-duplicate the selection (same company picked twice).
        seen: set[uuid.UUID] = set()
        stop_inputs: list[PlannerStopInput] = []
        for stop in request.stops:
            if stop.company_id in seen:
                continue
            seen.add(stop.company_id)
            stop_inputs.append(stop)
        if len(stop_inputs) < len(request.stops):
            warnings.append("Duplicate selections were removed.")

        max_stops = self.settings.route_max_stops
        if len(stop_inputs) > max_stops:
            raise PlannerError(
                422,
                "too_many_stops",
                f"{len(stop_inputs)} stops selected — a single day route supports at most {max_stops}. "
                "Remove some prospects and try again.",
            )

        start = self._validate_point(config.start_location, "Start location")
        end_location = config.resolved_end()
        end = self._validate_point(end_location, "End location") if end_location else None

        ids = [s.company_id for s in stop_inputs]
        rows = {
            r.company_id: r
            for r in self._company_rows(
                center=config.start_location, radius_miles=config.radius_miles, company_ids=ids
            )
        }
        unknown = [str(i) for i in ids if i not in rows]
        if unknown:
            raise PlannerError(404, "company_not_found", f"{len(unknown)} selected compan(ies) no longer exist. Refresh and try again.")

        if current_user.role != UserRole.ADMIN:
            not_mine = [rows[i] for i in ids if rows[i].assigned_user_id != current_user.id]
            if not_mine:
                raise PlannerError(
                    403,
                    "forbidden",
                    "You can only plan routes with prospects assigned to you.",
                    [{"company_id": str(r.company_id), "company_name": r.company_name} for r in not_mine],
                )

        missing = [rows[i] for i in ids if not rows[i].has_valid_coordinates]
        if missing:
            count = len(missing)
            raise PlannerError(
                422,
                "missing_coordinates",
                f"Route could not be generated because {count} selected prospect{'s' if count != 1 else ''} "
                f"{'do' if count != 1 else 'does'} not have valid coordinates.",
                [
                    {"company_id": str(r.company_id), "company_name": r.company_name, "address": r.address}
                    for r in missing
                ],
            )

        # The radius is a hard filter: prospects outside it are never sent to
        # Geoapify. They're reported back (not silently dropped) so the user
        # can widen the radius if they really meant to include them.
        outside = [rows[i] for i in ids if rows[i].within_radius is False]
        if outside:
            outside_ids = {r.company_id for r in outside}
            stop_inputs = [s for s in stop_inputs if s.company_id not in outside_ids]
            ids = [i for i in ids if i not in outside_ids]
            warnings.append(
                f"{len(outside)} selected prospect{'s are' if len(outside) != 1 else ' is'} outside the "
                f"{config.radius_miles:g}-mile radius and {'were' if len(outside) != 1 else 'was'} left out."
            )
            if not ids:
                raise PlannerError(
                    422,
                    "all_outside_radius",
                    f"None of the selected prospects are within {config.radius_miles:g} miles of the start "
                    "location. Increase the radius or choose a different start.",
                    [{"company_id": str(r.company_id), "company_name": r.company_name} for r in outside],
                )
        ordered_rows = [rows[i] for i in ids]
        by_point: dict[tuple[float, float], list[str]] = {}
        for r in ordered_rows:
            by_point.setdefault((round(r.latitude, 5), round(r.longitude, 5)), []).append(r.company_name)
        for names in by_point.values():
            if len(names) > 1:
                warnings.append(f"{' and '.join(names)} share the same location — they'll be visited back-to-back.")

        meetings = self._day_meetings(salesperson.id, config.date)
        day_length = _seconds_between(config.working_hours_start, config.working_hours_end)
        stops: list[opt.StopInput] = []
        for inp, row in zip(stop_inputs, ordered_rows):
            meeting = meetings.get(row.company_id)
            fixed_start = None
            duration = inp.duration_minutes or config.meeting_duration_minutes
            if meeting is not None and not meeting.is_planner_generated:
                fixed_start = _seconds_between(config.working_hours_start, meeting.start_time)
                duration = inp.duration_minutes or meeting.duration_minutes
            stops.append(
                opt.StopInput(
                    key=str(row.company_id),
                    duration_seconds=duration * 60,
                    priority=inp.priority or row.priority,
                    fixed_start=fixed_start,
                )
            )

        points = [start] + [(r.latitude, r.longitude) for r in ordered_rows] + ([end] if end else [])
        matrix, routing_engine, matrix_warnings = self._travel_matrix(points)
        warnings += matrix_warnings
        self._check_endpoints_reachable(matrix, len(ordered_rows), has_end=end is not None)

        day_config = opt.DayConfig(
            day_length_seconds=day_length,
            buffer_seconds=config.travel_buffer_minutes * 60,
            has_end=end is not None,
            allow_overtime=config.allow_overtime,
        )
        seeds = {}
        if request.optimize:
            seeds = self._geoapify_seed(start, end, ordered_rows, stops, day_config)
        result = opt.plan_day(stops, matrix, day_config, optimize=request.optimize, seeds=seeds)
        sim = result.simulation

        if not request.optimize:
            optimization_engine = "manual"
        elif result.used_seed == "geoapify":
            optimization_engine = "geoapify_route_planner"
        else:
            optimization_engine = "local"

        geometry = None
        if sim.stops and self.geoapify.is_configured:
            waypoints = [start] + [points[s.index] for s in sim.stops] + ([end] if end else [])
            try:
                geometry = self.geoapify.get_route(waypoints).geometry
            except GeoapifyError as exc:
                logger.warning("Route geometry unavailable: %s", exc)
                warnings.append("The road route line couldn't be drawn right now; times and order are still accurate.")

        contacts = self._first_contacts(ids)
        base = datetime.combine(config.date, config.working_hours_start)

        def clock(seconds: int) -> time:
            return (base + timedelta(seconds=seconds)).time()

        planned: list[PlannedStop] = []
        for seq, s in enumerate(sim.stops, start=1):
            row = ordered_rows[s.index - 1]
            stop_input = stops[s.index - 1]
            meeting = meetings.get(row.company_id)
            contact = contacts.get(row.company_id)
            planned.append(
                PlannedStop(
                    sequence=seq,
                    company_id=row.company_id,
                    location_id=row.location_id,
                    meeting_id=meeting.id if meeting else None,
                    meeting_status=meeting.status.value if meeting else None,
                    company_name=row.company_name,
                    address=row.address,
                    latitude=row.latitude,
                    longitude=row.longitude,
                    priority=stop_input.priority,
                    contact_name=contact.full_name if contact else None,
                    phone=row.phone,
                    duration_minutes=stop_input.duration_seconds // 60,
                    travel_time_seconds=s.travel_seconds,
                    distance_meters=round(s.distance_meters, 1),
                    arrival_time=clock(s.arrival),
                    meeting_start=clock(s.meeting_start),
                    meeting_end=clock(s.meeting_end),
                    departure_time=clock(s.meeting_end),
                    wait_seconds=s.wait_seconds,
                    late_seconds=s.late_seconds,
                    is_fixed_time=stop_input.fixed_start is not None,
                    outside_hours=s.outside_hours,
                    outside_radius=row.within_radius is False,
                )
            )
            if s.late_seconds:
                warnings.append(
                    f"Arrives {round(s.late_seconds / 60)} min after the scheduled "
                    f"{_format_clock(clock(stop_input.fixed_start))} meeting at {row.company_name}."
                )

        hours_label = f"{_format_clock(config.working_hours_start)}–{_format_clock(config.working_hours_end)}"
        name_by_id = {str(r.company_id): r for r in ordered_rows}
        unscheduled = [
            UnscheduledStopOut(
                company_id=r.company_id,
                company_name=r.company_name,
                priority=r.priority,
                reason="outside_radius",
                message=f"Outside the {config.radius_miles:g}-mile radius"
                + (f" ({r.distance_meters / METERS_PER_MILE:.1f} mi away)." if r.distance_meters else "."),
            )
            for r in outside
        ]
        for u in result.unscheduled:
            row = name_by_id[u.key]
            message = (
                f"Doesn't fit within working hours ({hours_label})."
                if u.reason == "does_not_fit"
                else "No drivable route to or from this location."
            )
            unscheduled.append(
                UnscheduledStopOut(
                    company_id=row.company_id,
                    company_name=row.company_name,
                    priority=stops[ids.index(row.company_id)].priority,
                    reason=u.reason,
                    message=message,
                )
            )
        not_fitting = [u for u in unscheduled if u.reason == "does_not_fit"]
        if not_fitting:
            warnings.insert(
                0,
                f"{len(stop_inputs)} meetings selected, but only {len(planned)} fit within the available time "
                f"({hours_label}).",
            )
        if any(u.reason == "unreachable" for u in unscheduled):
            warnings.insert(0, "Some selected locations can't be reached by road and were left out.")
        if sim.overtime and config.allow_overtime:
            warnings.append(
                f"This route runs {round(sim.overtime / 60)} min past {_format_clock(config.working_hours_end)}."
            )

        total_meeting = sum(stops[s.index - 1].duration_seconds for s in sim.stops)
        return RoutePlanOut(
            config=config,
            stops=planned,
            unscheduled=unscheduled,
            warnings=warnings,
            selected_count=len(stop_inputs) + len(outside),
            scheduled_count=len(planned),
            day_start=config.working_hours_start,
            day_finish=clock(sim.finish),
            return_travel_seconds=sim.return_travel_seconds,
            return_distance_meters=round(sim.return_distance_meters, 1),
            total_distance_meters=round(sim.total_distance, 1),
            total_driving_seconds=sim.total_travel,
            total_meeting_seconds=total_meeting,
            total_wait_seconds=sum(s.wait_seconds for s in sim.stops),
            total_duration_seconds=sim.finish,
            geometry=geometry,
            routing_engine=routing_engine,
            optimization_engine=optimization_engine,
        )

    @staticmethod
    def _check_endpoints_reachable(matrix: opt.Matrix, n_stops: int, *, has_end: bool) -> None:
        """If the start (or end) itself can't be reached by road, say so —
        otherwise every stop would be wrongly reported as unreachable."""
        stop_indices = range(1, n_stops + 1)
        if n_stops and all(matrix[0][i] is None and matrix[i][0] is None for i in stop_indices):
            raise PlannerError(
                422,
                "start_unreachable",
                "No drivable route exists from the start location. Choose a street address or business "
                "(not a landmark, peak or park) as the start.",
            )
        if has_end and n_stops and all(matrix[i][n_stops + 1] is None for i in stop_indices):
            raise PlannerError(
                422,
                "end_unreachable",
                "No drivable route exists to the end location. Choose a street address or business as the end.",
            )

    def _geoapify_seed(self, start, end, rows: list[_CompanyRow], stops: list[opt.StopInput], config: opt.DayConfig):
        """Ask Geoapify's Route Planner for an order suggestion. Failures are
        non-fatal: the in-app optimizer always runs regardless."""
        if not (self.geoapify.is_configured and self.settings.geoapify_route_planner_enabled and len(rows) >= 3):
            return {}
        jobs = [
            PlannerJob(
                id=str(row.company_id),
                location=(row.latitude, row.longitude),
                duration_seconds=stop.duration_seconds + config.buffer_seconds,
                priority=_GEOAPIFY_PRIORITY.get(stop.priority, 50),
            )
            for row, stop in zip(rows, stops)
        ]
        try:
            suggestion = self.geoapify.optimize_route(
                start,
                jobs,
                end=end,
                available_seconds=None if config.allow_overtime else config.day_length_seconds,
            )
        except GeoapifyError as exc:
            logger.warning("Geoapify route planner unavailable, using local optimizer only: %s", exc)
            return {}
        return {"geoapify": [i + 1 for i in suggestion.order]}

    # ------------------------------------------------------------------ persistence

    def save_plan(self, plan: RoutePlanOut, current_user: User, *, route: Route | None = None) -> Route:
        salesperson = self.resolve_salesperson(plan.config.salesperson_id, current_user)
        config = plan.config
        if route is not None and (route.salesperson_id != salesperson.id or route.date != config.date):
            raise PlannerError(
                422, "route_identity_changed", "A saved route's salesperson and date can't be changed — save it as a new route."
            )
        if not plan.stops:
            raise PlannerError(422, "empty_route", "There are no scheduled stops to save.")

        company_ids = [s.company_id for s in plan.stops]
        rows = {r.company_id: r for r in self._company_rows(company_ids=company_ids)}
        if any(cid not in rows for cid in company_ids):
            raise PlannerError(404, "company_not_found", "Some stops reference companies that no longer exist.")
        if current_user.role != UserRole.ADMIN and any(
            rows[cid].assigned_user_id != current_user.id for cid in company_ids
        ):
            raise PlannerError(403, "forbidden", "You can only save routes with prospects assigned to you.")

        if route is None:
            route = (
                self.db.query(Route)
                .filter(Route.salesperson_id == salesperson.id, Route.date == config.date)
                .first()
            )
        if route is None:
            route = Route(salesperson_id=salesperson.id, date=config.date, status=RouteStatus.DRAFT)
            self.db.add(route)

        previous_meeting_ids = {s.meeting_id for s in route.stops if s.meeting_id}

        route.name = config.name
        route.start_location = config.start_location.model_dump()
        end_location = config.resolved_end()
        route.end_location = end_location.model_dump() if end_location else None
        route.end_mode = config.end_mode
        route.radius_miles = config.radius_miles
        route.working_hours_start = config.working_hours_start
        route.working_hours_end = config.working_hours_end
        route.meeting_duration_minutes = config.meeting_duration_minutes
        route.travel_buffer_minutes = config.travel_buffer_minutes
        route.allow_overtime = config.allow_overtime
        route.estimated_distance_meters = plan.total_distance_meters
        route.estimated_duration_seconds = plan.total_driving_seconds
        route.total_meeting_seconds = plan.total_meeting_seconds
        route.total_duration_seconds = plan.total_duration_seconds
        route.return_travel_seconds = plan.return_travel_seconds
        route.return_distance_meters = plan.return_distance_meters
        route.geometry = plan.geometry
        route.unscheduled = [u.model_dump(mode="json") for u in plan.unscheduled]
        route.warnings = plan.warnings
        route.optimization_engine = f"{plan.routing_engine}:{plan.optimization_engine}"
        route.stops.clear()
        self.db.flush()

        meetings = self._day_meetings(salesperson.id, config.date)
        contacts = self._first_contacts(company_ids)
        meeting_service = MeetingService(self.db)
        used_meeting_ids: set[uuid.UUID] = set()
        for stop in plan.stops:
            row = rows[stop.company_id]
            meeting = meetings.get(stop.company_id)
            if meeting is None:
                contact = contacts.get(stop.company_id)
                meeting = meeting_service.create_meeting(
                    MeetingCreate(
                        company_id=stop.company_id,
                        contact_id=contact.id if contact else None,
                        salesperson_id=salesperson.id,
                        date=config.date,
                        start_time=stop.meeting_start,
                        duration_minutes=stop.duration_minutes,
                    ),
                    created_by_id=current_user.id,
                    is_planner_generated=True,
                )
            elif meeting.is_planner_generated:
                meeting.start_time = stop.meeting_start
                meeting.duration_minutes = stop.duration_minutes
                meeting.end_time = stop.meeting_end
            # A meeting can only be a stop on one route (route_stops.meeting_id is unique).
            self.db.query(RouteStop).filter(RouteStop.meeting_id == meeting.id).delete(synchronize_session=False)
            used_meeting_ids.add(meeting.id)
            route.stops.append(
                RouteStop(
                    meeting_id=meeting.id,
                    company_id=stop.company_id,
                    location_id=row.location_id,
                    sequence=stop.sequence,
                    arrival_time=stop.arrival_time,
                    departure_time=stop.departure_time,
                    meeting_start=stop.meeting_start,
                    meeting_end=stop.meeting_end,
                    duration_minutes=stop.duration_minutes,
                    wait_seconds=stop.wait_seconds,
                    travel_time_seconds=stop.travel_time_seconds,
                    distance_meters=stop.distance_meters,
                    priority=stop.priority,
                    is_fixed_time=stop.is_fixed_time,
                    outside_hours=stop.outside_hours,
                    company_name=row.company_name,
                    address=row.address,
                    latitude=row.latitude,
                    longitude=row.longitude,
                )
            )

        self._discard_provisional_meetings(previous_meeting_ids - used_meeting_ids)
        self.db.flush()
        return route

    def _discard_provisional_meetings(self, meeting_ids: set[uuid.UUID]) -> None:
        """Meetings the planner created for stops that are no longer on the
        route. Only untouched planner placeholders are removed — anything a
        person confirmed, completed or created by hand is kept."""
        if not meeting_ids:
            return
        self.db.query(Meeting).filter(
            Meeting.id.in_(meeting_ids),
            Meeting.is_planner_generated.is_(True),
            Meeting.status == MeetingStatus.SCHEDULED,
        ).delete(synchronize_session=False)

    def delete_route(self, route: Route) -> None:
        meeting_ids = {s.meeting_id for s in route.stops if s.meeting_id}
        self.db.delete(route)
        self.db.flush()
        self._discard_provisional_meetings(meeting_ids)
        self.db.flush()

    def load_route(self, route_id: uuid.UUID, current_user: User) -> Route:
        route = (
            self.db.query(Route)
            .options(
                joinedload(Route.salesperson),
                joinedload(Route.stops).joinedload(RouteStop.meeting).joinedload(Meeting.location),
                joinedload(Route.stops).joinedload(RouteStop.meeting).joinedload(Meeting.contact),
                joinedload(Route.stops).joinedload(RouteStop.meeting).joinedload(Meeting.company),
            )
            .filter(Route.id == route_id)
            .first()
        )
        if route is None:
            raise PlannerError(404, "route_not_found", "Route not found")
        self.ensure_can_access(route, current_user)
        return route

    def list_routes(
        self,
        current_user: User,
        *,
        salesperson_id: uuid.UUID | None = None,
        date_from: date_type | None = None,
        date_to: date_type | None = None,
        limit: int = 100,
    ) -> list[RouteListItem]:
        query = self.db.query(Route).options(joinedload(Route.salesperson), joinedload(Route.stops))
        if current_user.role != UserRole.ADMIN:
            query = query.filter(Route.salesperson_id == current_user.id)
        elif salesperson_id is not None:
            query = query.filter(Route.salesperson_id == salesperson_id)
        if date_from:
            query = query.filter(Route.date >= date_from)
        if date_to:
            query = query.filter(Route.date <= date_to)
        routes = query.order_by(Route.date.desc(), Route.updated_at.desc()).limit(limit).all()
        # joinedload on a collection + limit is safe in SA 2.x (it subqueries), but de-dupe defensively.
        unique = list(dict.fromkeys(routes))
        return [
            RouteListItem(
                id=r.id,
                name=r.name,
                date=r.date,
                salesperson_id=r.salesperson_id,
                salesperson_name=r.salesperson.name if r.salesperson else None,
                status=r.status,
                stop_count=len(r.stops),
                start_name=(r.start_location or {}).get("name"),
                total_distance_meters=r.estimated_distance_meters,
                total_driving_seconds=r.estimated_duration_seconds,
                total_duration_seconds=r.total_duration_seconds,
                updated_at=r.updated_at,
            )
            for r in unique
        ]

    def to_saved_out(self, route: Route) -> SavedRouteOut:
        start = NamedLocation(**route.start_location)
        end = NamedLocation(**route.end_location) if route.end_location else None
        end_mode = route.end_mode or ("custom" if end else "none")
        first = route.stops[0] if route.stops else None
        hours_start = route.working_hours_start or (first.arrival_time if first and first.arrival_time else time(9, 0))
        hours_end = route.working_hours_end or time(17, 0)
        if hours_end <= hours_start:
            hours_end = time(23, 59)
        config = RoutePlanConfig(
            salesperson_id=route.salesperson_id,
            date=route.date,
            name=route.name,
            start_location=start,
            end_mode=end_mode,
            end_location=end if end_mode == "custom" else None,
            working_hours_start=hours_start,
            working_hours_end=hours_end,
            meeting_duration_minutes=route.meeting_duration_minutes or 25,
            travel_buffer_minutes=route.travel_buffer_minutes or 0,
            radius_miles=route.radius_miles or 25,
            allow_overtime=route.allow_overtime,
        )

        company_ids = [
            s.company_id or (s.meeting.company_id if s.meeting else None)
            for s in route.stops
            if s.company_id or s.meeting
        ]
        current = {r.company_id: r for r in self._company_rows(company_ids=company_ids)} if company_ids else {}
        planned: list[PlannedStop] = []
        stale = False
        for stop in sorted(route.stops, key=lambda s: s.sequence):
            meeting = stop.meeting
            company_id = stop.company_id or (meeting.company_id if meeting else None)
            if company_id is None:
                stale = True
                continue
            now = current.get(company_id)
            lat = stop.latitude if stop.latitude is not None else (now.latitude if now else None)
            lng = stop.longitude if stop.longitude is not None else (now.longitude if now else None)
            changed = now is None or (
                now.latitude is None
                or lat is None
                or abs(now.latitude - lat) > _LOCATION_CHANGE_TOLERANCE
                or abs(now.longitude - lng) > _LOCATION_CHANGE_TOLERANCE
            )
            stale = stale or changed
            meeting_start = stop.meeting_start or stop.arrival_time or hours_start
            meeting_end = stop.meeting_end or stop.departure_time or meeting_start
            planned.append(
                PlannedStop(
                    sequence=stop.sequence,
                    company_id=company_id,
                    location_id=stop.location_id,
                    meeting_id=stop.meeting_id,
                    meeting_status=meeting.status.value if meeting else None,
                    company_name=stop.company_name or (now.company_name if now else "Unknown company"),
                    address=stop.address or (now.address if now else None),
                    latitude=lat,
                    longitude=lng,
                    priority=stop.priority or (now.priority if now else "medium"),
                    contact_name=meeting.contact.full_name if meeting and meeting.contact else None,
                    phone=now.phone if now else None,
                    duration_minutes=stop.duration_minutes or (meeting.duration_minutes if meeting else 25),
                    travel_time_seconds=stop.travel_time_seconds or 0,
                    distance_meters=stop.distance_meters or 0,
                    arrival_time=stop.arrival_time or meeting_start,
                    meeting_start=meeting_start,
                    meeting_end=meeting_end,
                    departure_time=stop.departure_time or meeting_end,
                    wait_seconds=stop.wait_seconds or 0,
                    is_fixed_time=stop.is_fixed_time,
                    outside_hours=stop.outside_hours,
                    location_changed=changed,
                )
            )

        total_meeting = route.total_meeting_seconds
        if total_meeting is None:
            total_meeting = sum(p.duration_minutes * 60 for p in planned)
        last = planned[-1].departure_time if planned else hours_start
        finish_seconds = route.total_duration_seconds
        if finish_seconds is None:
            finish_seconds = max(0, _seconds_between(hours_start, last)) + (route.return_travel_seconds or 0)
        finish = (datetime.combine(route.date, hours_start) + timedelta(seconds=finish_seconds)).time()
        engine = route.optimization_engine or "legacy:local"
        routing_engine, _, optimization_engine = engine.partition(":")
        return SavedRouteOut(
            id=route.id,
            status=route.status,
            salesperson_name=route.salesperson.name if route.salesperson else None,
            created_at=route.created_at,
            updated_at=route.updated_at,
            is_stale=stale,
            config=config,
            stops=planned,
            unscheduled=[UnscheduledStopOut(**u) for u in (route.unscheduled or [])],
            warnings=list(route.warnings or []),
            selected_count=len(planned) + len(route.unscheduled or []),
            scheduled_count=len(planned),
            day_start=hours_start,
            day_finish=finish,
            return_travel_seconds=route.return_travel_seconds or 0,
            return_distance_meters=route.return_distance_meters or 0,
            total_distance_meters=route.estimated_distance_meters or 0,
            total_driving_seconds=route.estimated_duration_seconds or 0,
            total_meeting_seconds=total_meeting,
            total_wait_seconds=sum(p.wait_seconds for p in planned),
            total_duration_seconds=finish_seconds,
            geometry=route.geometry,
            routing_engine=routing_engine or "legacy",
            optimization_engine=optimization_engine or "local",
        )

    def recalculate(self, route: Route, current_user: User, *, optimize: bool) -> RoutePlanOut:
        """Re-plan a saved route against *current* company locations without
        saving — the caller decides whether to keep the new plan."""
        saved = self.to_saved_out(route)
        stops = [
            PlannerStopInput(company_id=s.company_id, duration_minutes=s.duration_minutes) for s in saved.stops
        ] + [PlannerStopInput(company_id=u.company_id) for u in saved.unscheduled]
        if not stops:
            raise PlannerError(422, "empty_route", "This route has no stops to recalculate.")
        config = saved.config.model_dump()
        # End locations are no longer offered; recalculating drops any old one.
        config.update(end_mode="none", end_location=None)
        request = OptimizeRouteRequest(**config, stops=stops, optimize=optimize)
        return self.build_plan(request, current_user)

    # ------------------------------------------------------------------ geocoding

    def geocode_missing(self, company_ids: list[uuid.UUID], current_user: User) -> list[GeocodeMissingResult]:
        """Geocode companies that have an address but no usable coordinates,
        through the same verification rules as import (never overwriting a
        verified location, never auto-accepting an ambiguous match)."""
        if self.geoapify.is_configured:
            from app.providers.location.geoapify import GeoapifyLocationProvider

            provider = GeoapifyLocationProvider()
        else:
            provider = get_location_provider()
            if provider.name == "fallback_estimate":
                raise GeoapifyNotConfiguredError("no geocoding provider configured")

        companies = (
            self.db.query(Company)
            .options(joinedload(Company.locations), joinedload(Company.prospect))
            .filter(Company.id.in_(company_ids))
            .all()
        )
        if current_user.role != UserRole.ADMIN:
            for company in companies:
                if company.prospect is None or company.prospect.assigned_user_id != current_user.id:
                    raise PlannerError(403, "forbidden", "You can only locate prospects assigned to you.")

        service = LocationService(self.db, provider)
        results = []
        for company in companies:
            location = next((loc for loc in company.locations if loc.is_primary), None)
            if (
                location is not None
                and location.verification_status == VerificationStatus.VERIFIED
                and location.latitude is not None
            ):
                results.append(
                    GeocodeMissingResult(
                        company_id=company.id,
                        company_name=company.name,
                        status="already_verified",
                        latitude=location.latitude,
                        longitude=location.longitude,
                    )
                )
                continue
            raw = location.address_line_1 if location else None
            city = location.city if location else None
            state = location.state if location else None
            postal = location.postal_code if location else None
            if raw and not (city and state):
                parsed = parse_combined_address(raw)
                if parsed["city"] and parsed["state"]:
                    raw, city, state = parsed["street"], parsed["city"], parsed["state"]
                    postal = postal or parsed["postal_code"]
            if not (raw or city):
                results.append(
                    GeocodeMissingResult(
                        company_id=company.id,
                        company_name=company.name,
                        status="failed",
                        message="No address on file — add one on the company page.",
                    )
                )
                continue
            try:
                found, candidates, reason = service.verify_company_location(
                    company_id=company.id,
                    company_name=company.name,
                    raw_address=raw,
                    city=city,
                    state=state,
                    postal_code=postal,
                    country=location.country if location else None,
                )
            except (GeoapifyNotConfiguredError, GeoapifyAuthError):
                raise  # affects every company — report once, clearly
            except Exception as exc:  # transient provider/network failure for this one company
                logger.warning("Geocoding %s failed: %s", company.id, type(exc).__name__)
                results.append(
                    GeocodeMissingResult(
                        company_id=company.id, company_name=company.name, status="failed",
                        message="Location lookup failed. Try again later.",
                    )
                )
                continue
            if found is not None:
                results.append(
                    GeocodeMissingResult(
                        company_id=company.id,
                        company_name=company.name,
                        status="verified",
                        latitude=found.latitude,
                        longitude=found.longitude,
                    )
                )
            else:
                note = reason or (
                    f"{len(candidates)} possible matches — pick the right one on the prospect page."
                    if candidates
                    else "No confident match found for this address."
                )
                service.mark_needs_verification(
                    company_id=company.id, raw_address=raw, notes=note, city=city, state=state, postal_code=postal
                )
                results.append(
                    GeocodeMissingResult(
                        company_id=company.id, company_name=company.name, status="needs_review", message=note
                    )
                )
        self.db.flush()
        return results
