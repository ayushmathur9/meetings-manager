"""Auto-planning for a salesperson's day: "Plan My Day".

Given a starting location, territory (radius/industry/status filters), a
target meeting count and working hours, this picks a geographically sensible
set of eligible prospects, schedules meetings for them around any fixed
meetings already on the calendar that day, and hands off to RouteService for
the actual stop ordering/timing (nearest-neighbor + 2-opt).

Only prospects with a verified (or explicitly included) location are ever
routed — never a guessed address.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.location import VerificationStatus
from app.models.meeting import Meeting, MeetingStatus
from app.models.route import RouteStop
from app.providers.location.base import LocationProvider
from app.schemas.meeting import MeetingCreate
from app.schemas.prospect import ProspectFilters
from app.schemas.route import GenerateRouteRequest, PlanDayRequest, PlanDaySummary
from app.services.meeting_service import MeetingService
from app.services.prospect_service import ProspectService
from app.services.route_service import RouteService

_ACCEPTABLE_VERIFICATION = {VerificationStatus.VERIFIED, VerificationStatus.NEEDS_REVIEW}


class RoutePlanningService:
    def __init__(self, db: Session, location_provider: LocationProvider) -> None:
        self.db = db
        self.location_provider = location_provider
        self.route_service = RouteService(db, location_provider)
        self.meeting_service = MeetingService(db)
        self.prospect_service = ProspectService(db)

    def plan_day(self, payload: PlanDayRequest, *, created_by_id: uuid.UUID):
        filters = ProspectFilters(
            industry=payload.industry,
            status=payload.status,
            assigned_user_id=payload.salesperson_id,
            center_lat=payload.start_location.latitude,
            center_lng=payload.start_location.longitude,
            radius_miles=payload.radius_miles,
            page=1,
            page_size=500,
        )
        prospects, eligible_count = self.prospect_service.list_prospects(
            filters, restrict_to_user=payload.salesperson_id
        )
        in_territory_count = len(prospects)

        located = [p for p in prospects if p["latitude"] is not None and p["longitude"] is not None]
        if payload.include_unverified:
            verified = located
        else:
            verified = [p for p in located if p["verification_status"] in _ACCEPTABLE_VERIFICATION]
        excluded_unverified_count = len(located) - len(verified)
        verified_count = len(verified)

        # Meetings already on this salesperson's day split into two groups:
        #  - genuinely fixed: a person created/confirmed these for a real
        #    time, so they must never move.
        #  - provisional: the planner auto-scheduled these on an earlier
        #    "Plan My Day" run with a placeholder time that was never meant
        #    to be final. Re-planning discards them and lets the normal
        #    candidate selection below re-pick and re-time them properly —
        #    otherwise their placeholder time would get locked in as if it
        #    were a real commitment (this was a real, observed bug).
        existing_meetings = (
            self.db.query(Meeting)
            .filter(
                Meeting.salesperson_id == payload.salesperson_id,
                Meeting.date == payload.date,
                Meeting.status.notin_([MeetingStatus.CANCELLED, MeetingStatus.NO_SHOW]),
            )
            .all()
        )
        fixed_meetings = [m for m in existing_meetings if not m.is_planner_generated]
        provisional_meetings = [m for m in existing_meetings if m.is_planner_generated]
        if provisional_meetings:
            provisional_ids = [m.id for m in provisional_meetings]
            self.db.query(RouteStop).filter(RouteStop.meeting_id.in_(provisional_ids)).delete(
                synchronize_session=False
            )
            self.db.query(Meeting).filter(Meeting.id.in_(provisional_ids)).delete(synchronize_session=False)
            self.db.flush()

        fixed_meeting_ids = {m.id for m in fixed_meetings}
        fixed_company_ids = {m.company_id for m in fixed_meetings}

        candidates = [p for p in verified if p["company_id"] not in fixed_company_ids]

        slots_available = max(payload.target_meetings - len(fixed_meetings), 0)
        candidate_pool = candidates[: max(slots_available * 3, slots_available)]

        chosen_meeting_ids = list(fixed_meeting_ids)
        newly_created_ids: list[uuid.UUID] = []
        if slots_available > 0 and candidate_pool:
            selected = self._select_and_order_within_hours(
                payload=payload,
                candidates=candidate_pool,
                fixed_meetings=fixed_meetings,
                slots_available=slots_available,
            )
            for company_id, contact_id in selected:
                meeting = self.meeting_service.create_meeting(
                    MeetingCreate(
                        company_id=company_id,
                        contact_id=contact_id,
                        salesperson_id=payload.salesperson_id,
                        date=payload.date,
                        start_time=payload.working_hours_start,
                        duration_minutes=payload.meeting_duration_minutes,
                    ),
                    created_by_id=created_by_id,
                    is_planner_generated=True,
                )
                newly_created_ids.append(meeting.id)
            chosen_meeting_ids += newly_created_ids

        scheduled_count = len(chosen_meeting_ids)
        if scheduled_count == 0:
            if eligible_count == 0:
                raise ValueError(
                    "This salesperson has no prospects assigned to them. Assign prospects "
                    "on the Prospects page before planning a day."
                )
            if in_territory_count == 0:
                raise ValueError(
                    f"{eligible_count} prospect(s) are assigned to this salesperson, but none "
                    f"fall within {payload.radius_miles} miles of the starting location. Try a larger radius."
                )
            if verified_count == 0:
                raise ValueError(
                    f"{in_territory_count} prospect(s) are in this territory, but none have a "
                    "verified location yet. Verify their addresses on the Prospects page, or "
                    "include unverified locations."
                )
            raise ValueError(
                f"{verified_count} verified prospect(s) were found, but none could be scheduled "
                "within working hours. Try extending working hours or reducing the target meeting count."
            )

        generate_payload = GenerateRouteRequest(
            salesperson_id=payload.salesperson_id,
            date=payload.date,
            start_location=payload.start_location,
            end_location=payload.end_location,
            working_hours_start=payload.working_hours_start,
            working_hours_end=payload.working_hours_end,
            meeting_duration_minutes=payload.meeting_duration_minutes,
            travel_buffer_minutes=payload.travel_buffer_minutes,
            meeting_ids=chosen_meeting_ids,
        )
        route = self.route_service.generate_route(generate_payload, fixed_meeting_ids=fixed_meeting_ids)

        last_stop = route.stops[-1] if route.stops else None
        last_departure = last_stop.departure_time if last_stop else None
        fits = True
        available_seconds = 0
        if last_departure is not None:
            end_dt = datetime.combine(payload.date, payload.working_hours_end)
            departure_dt = datetime.combine(payload.date, last_departure)
            available_seconds = int((end_dt - departure_dt).total_seconds())
            fits = available_seconds >= 0
            available_seconds = max(available_seconds, 0)
        else:
            start_dt = datetime.combine(payload.date, payload.working_hours_start)
            end_dt = datetime.combine(payload.date, payload.working_hours_end)
            available_seconds = int((end_dt - start_dt).total_seconds())

        summary = PlanDaySummary(
            eligible_count=eligible_count,
            verified_count=verified_count,
            in_territory_count=in_territory_count,
            scheduled_count=scheduled_count,
            excluded_unverified_count=excluded_unverified_count,
            fixed_meeting_count=len(fixed_meetings),
            working_hours_end=payload.working_hours_end,
            last_stop_departure=last_departure,
            fits_within_working_hours=fits,
            available_seconds=available_seconds,
        )
        return route, summary

    def _select_and_order_within_hours(
        self, *, payload: PlanDayRequest, candidates: list[dict], fixed_meetings: list[Meeting], slots_available: int
    ) -> list[tuple[uuid.UUID, uuid.UUID | None]]:
        """Greedily grow the candidate set, keeping only as many as fit in
        working hours once ordered/timed, stopping once the target is hit
        or the day is full.
        """
        contact_by_company = self._first_contact_ids([c["company_id"] for c in candidates])

        chosen: list[dict] = []
        for candidate in candidates:
            if len(chosen) >= slots_available:
                break
            trial = chosen + [candidate]
            if self._fits_in_working_hours(payload, trial, fixed_meetings):
                chosen.append(candidate)

        return [(c["company_id"], contact_by_company.get(c["company_id"])) for c in chosen]

    def _fits_in_working_hours(
        self, payload: PlanDayRequest, trial_candidates: list[dict], fixed_meetings: list[Meeting]
    ) -> bool:
        located_fixed_meetings = [
            m for m in fixed_meetings if m.location and m.location.latitude is not None
        ]

        points = [(payload.start_location.latitude, payload.start_location.longitude)]
        points += [(c["latitude"], c["longitude"]) for c in trial_candidates]
        points += [(m.location.latitude, m.location.longitude) for m in located_fixed_meetings]

        matrix = self.location_provider.calculate_travel_time_matrix(points, points)
        order = self.route_service._nearest_neighbor_order(matrix, len(points) - 1)
        order = self.route_service._two_opt(order, matrix)

        durations = [payload.meeting_duration_minutes] * len(trial_candidates)
        durations += [m.duration_minutes for m in located_fixed_meetings]

        current_time = datetime.combine(payload.date, payload.working_hours_start)
        prev_index = 0
        for idx in order:
            travel = matrix[prev_index][idx]
            travel_seconds = travel.duration_seconds if travel else 0
            current_time += timedelta(seconds=travel_seconds)
            current_time += timedelta(minutes=durations[idx - 1])
            current_time += timedelta(minutes=payload.travel_buffer_minutes)
            prev_index = idx

        end_dt = datetime.combine(payload.date, payload.working_hours_end)
        return current_time <= end_dt

    def _first_contact_ids(self, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID | None]:
        from app.models.contact import Contact

        if not company_ids:
            return {}
        rows = (
            self.db.query(Contact.company_id, Contact.id)
            .filter(Contact.company_id.in_(company_ids))
            .order_by(Contact.company_id)
            .all()
        )
        result: dict[uuid.UUID, uuid.UUID | None] = {cid: None for cid in company_ids}
        for company_id, contact_id in rows:
            if result.get(company_id) is None:
                result[company_id] = contact_id
        return result
