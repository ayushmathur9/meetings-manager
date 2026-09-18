import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.error_handling import translate_provider_errors
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.meeting import Meeting
from app.models.route import Route, RouteStop
from app.models.user import User
from app.providers.location import get_location_provider
from app.schemas.route import (
    GenerateRouteRequest,
    PlanDayRequest,
    PlanDayResult,
    ReorderRouteRequest,
    RouteOut,
    RouteStopOut,
)
from app.services.activity_service import ActivityService
from app.services.route_planning_service import RoutePlanningService
from app.services.route_service import RouteService

router = APIRouter(prefix="/routes", tags=["routes"])


def _to_route_out(route: Route) -> RouteOut:
    stops = []
    for stop in sorted(route.stops, key=lambda s: s.sequence):
        meeting = stop.meeting
        stops.append(
            RouteStopOut(
                id=stop.id,
                meeting_id=stop.meeting_id,
                sequence=stop.sequence,
                arrival_time=stop.arrival_time,
                departure_time=stop.departure_time,
                travel_time_seconds=stop.travel_time_seconds,
                distance_meters=stop.distance_meters,
                company_name=meeting.company.name,
                company_id=meeting.company_id,
                address_line_1=meeting.location.address_line_1 if meeting.location else None,
                city=meeting.location.city if meeting.location else None,
                state=meeting.location.state if meeting.location else None,
                latitude=meeting.location.latitude if meeting.location else None,
                longitude=meeting.location.longitude if meeting.location else None,
                meeting_status=meeting.status.value,
                contact_name=meeting.contact.full_name if meeting.contact else None,
            )
        )
    return RouteOut(
        id=route.id,
        salesperson_id=route.salesperson_id,
        date=route.date,
        start_location=route.start_location,
        end_location=route.end_location,
        status=route.status,
        estimated_distance_meters=route.estimated_distance_meters,
        estimated_duration_seconds=route.estimated_duration_seconds,
        stops=stops,
    )


def _load_route(db: Session, route_id: uuid.UUID) -> Route:
    route = (
        db.query(Route)
        .options(
            joinedload(Route.stops).joinedload(RouteStop.meeting).joinedload(Meeting.company),
            joinedload(Route.stops).joinedload(RouteStop.meeting).joinedload(Meeting.location),
            joinedload(Route.stops).joinedload(RouteStop.meeting).joinedload(Meeting.contact),
        )
        .filter(Route.id == route_id)
        .first()
    )
    if route is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Route not found")
    return route


@router.post("/generate", response_model=RouteOut)
def generate_route(
    payload: GenerateRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RouteOut:
    service = RouteService(db, get_location_provider())
    try:
        with translate_provider_errors():
            route = service.generate_route(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="route",
        entity_id=route.id,
        action="generated",
        metadata={"stop_count": len(route.stops)},
    )
    db.commit()
    route = _load_route(db, route.id)
    return _to_route_out(route)


@router.post("/plan", response_model=PlanDayResult)
def plan_day(
    payload: PlanDayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanDayResult:
    service = RoutePlanningService(db, get_location_provider())
    try:
        with translate_provider_errors():
            route, summary = service.plan_day(payload, created_by_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="route",
        entity_id=route.id,
        action="planned",
        metadata={"stop_count": len(route.stops), "target_meetings": payload.target_meetings},
    )
    db.commit()
    route = _load_route(db, route.id)
    return PlanDayResult(route=_to_route_out(route), summary=summary)


@router.get("/by-date", response_model=RouteOut | None)
def get_route_by_date(
    salesperson_id: uuid.UUID,
    date: date_type,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RouteOut | None:
    service = RouteService(db, get_location_provider())
    route = service.get_route_for_day(salesperson_id, date)
    if route is None:
        return None
    route = _load_route(db, route.id)
    return _to_route_out(route)


@router.get("/{route_id}", response_model=RouteOut)
def get_route(
    route_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RouteOut:
    route = _load_route(db, route_id)
    return _to_route_out(route)


@router.patch("/{route_id}/reorder", response_model=RouteOut)
def reorder_route(
    route_id: uuid.UUID,
    payload: ReorderRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RouteOut:
    route = _load_route(db, route_id)
    service = RouteService(db, get_location_provider())
    with translate_provider_errors():
        route = service.reorder_route(route, payload.ordered_meeting_ids)
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="route",
        entity_id=route.id,
        action="reordered",
    )
    db.commit()
    route = _load_route(db, route.id)
    return _to_route_out(route)
