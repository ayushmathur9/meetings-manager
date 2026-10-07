import uuid
from contextlib import contextmanager
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.api.error_handling import translate_provider_errors
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.meeting import Meeting
from app.models.route import Route, RouteStop
from app.models.user import User, UserRole
from app.providers.location import get_location_provider
from app.schemas.route import (
    CandidatesOut,
    CandidatesRequest,
    GenerateRouteRequest,
    GeocodeMissingRequest,
    GeocodeMissingResult,
    OptimizeRouteRequest,
    PlanDayRequest,
    PlanDayResult,
    RecalculateRouteRequest,
    ReorderRouteRequest,
    RouteListItem,
    RouteOut,
    RoutePlanOut,
    RouteStopOut,
    SavedRouteOut,
    SaveRouteRequest,
    UpdateRouteRequest,
)
from app.services.activity_service import ActivityService
from app.services.route_planning_service import RoutePlanningService
from app.services.route_service import RouteService
from app.services.sales_day_planner import PlannerError, SalesDayPlanner

router = APIRouter(prefix="/routes", tags=["routes"])


@contextmanager
def _planner_errors(db: Session):
    """Map planner/provider/database failures to clean, user-safe responses."""
    try:
        with translate_provider_errors():
            yield
    except PlannerError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.detail())
    except SQLAlchemyError:
        db.rollback()
        import logging

        logging.getLogger("app.errors").exception("Database error in route planner")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"code": "database_error", "message": "The route couldn't be saved because of a database error. Please try again."},
        )


def _require_self_or_admin(salesperson_id: uuid.UUID, current_user: User) -> None:
    if current_user.role != UserRole.ADMIN and salesperson_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own routes")


# ---------------------------------------------------------------------------
# Sales-day route planner
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=CandidatesOut)
def preview_candidates(
    payload: CandidatesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CandidatesOut:
    """Prospects around the start location, classified inside / outside the
    radius / missing coordinates (PostGIS — no external API calls)."""
    with _planner_errors(db):
        return SalesDayPlanner(db).find_candidates(payload, current_user)


@router.post("/optimize", response_model=RoutePlanOut)
def optimize_route(
    payload: OptimizeRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoutePlanOut:
    """Order (when `optimize`) and schedule the selected stops. Nothing is saved."""
    with _planner_errors(db):
        return SalesDayPlanner(db).build_plan(payload, current_user)


@router.post("/geocode-missing", response_model=list[GeocodeMissingResult])
def geocode_missing(
    payload: GeocodeMissingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GeocodeMissingResult]:
    with _planner_errors(db):
        results = SalesDayPlanner(db).geocode_missing(payload.company_ids, current_user)
        db.commit()
    return results


@router.get("", response_model=list[RouteListItem])
def list_routes(
    salesperson_id: uuid.UUID | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RouteListItem]:
    return SalesDayPlanner(db).list_routes(
        current_user, salesperson_id=salesperson_id, date_from=date_from, date_to=date_to
    )


@router.post("", response_model=SavedRouteOut, status_code=status.HTTP_201_CREATED)
def save_route(
    payload: SaveRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedRouteOut:
    """Save a plan as the salesperson's route for that day (replacing any
    existing route for the same day) and sync the day's meetings."""
    planner = SalesDayPlanner(db)
    with _planner_errors(db):
        route = planner.save_plan(payload.plan, current_user)
        if payload.status is not None:
            route.status = payload.status
        ActivityService(db).log(
            user_id=current_user.id,
            entity_type="route",
            entity_id=route.id,
            action="saved",
            metadata={"stop_count": len(payload.plan.stops), "date": payload.plan.config.date.isoformat()},
        )
        db.commit()
        return planner.to_saved_out(planner.load_route(route.id, current_user))


@router.get("/by-date", response_model=RouteOut | None)
def get_route_by_date(
    salesperson_id: uuid.UUID,
    date: date_type,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RouteOut | None:
    _require_self_or_admin(salesperson_id, current_user)
    service = RouteService(db, get_location_provider())
    route = service.get_route_for_day(salesperson_id, date)
    if route is None:
        return None
    route = _load_route(db, route.id)
    return _to_route_out(route)


@router.get("/{route_id}", response_model=SavedRouteOut)
def get_route(
    route_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedRouteOut:
    planner = SalesDayPlanner(db)
    with _planner_errors(db):
        return planner.to_saved_out(planner.load_route(route_id, current_user))


@router.patch("/{route_id}", response_model=SavedRouteOut)
def update_route(
    route_id: uuid.UUID,
    payload: UpdateRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedRouteOut:
    planner = SalesDayPlanner(db)
    with _planner_errors(db):
        route = planner.load_route(route_id, current_user)
        if payload.plan is not None:
            route = planner.save_plan(payload.plan, current_user, route=route)
        if payload.name is not None:
            route.name = payload.name
        if payload.status is not None:
            route.status = payload.status
        ActivityService(db).log(
            user_id=current_user.id, entity_type="route", entity_id=route.id, action="updated"
        )
        db.commit()
        return planner.to_saved_out(planner.load_route(route.id, current_user))


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    planner = SalesDayPlanner(db)
    with _planner_errors(db):
        route = planner.load_route(route_id, current_user)
        planner.delete_route(route)
        ActivityService(db).log(
            user_id=current_user.id, entity_type="route", entity_id=route_id, action="deleted"
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{route_id}/recalculate", response_model=RoutePlanOut)
def recalculate_route(
    route_id: uuid.UUID,
    payload: RecalculateRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoutePlanOut:
    """Re-plan a saved route using current company locations. Returns a new
    plan without saving it — PATCH the route with it to keep it."""
    planner = SalesDayPlanner(db)
    with _planner_errors(db):
        route = planner.load_route(route_id, current_user)
        return planner.recalculate(route, current_user, optimize=payload.optimize)


# ---------------------------------------------------------------------------
# Legacy endpoints (meeting-based routes) — kept for backwards compatibility
# ---------------------------------------------------------------------------


def _to_route_out(route: Route) -> RouteOut:
    stops = []
    for stop in sorted(route.stops, key=lambda s: s.sequence):
        meeting = stop.meeting
        if meeting is None:
            continue
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
    _require_self_or_admin(payload.salesperson_id, current_user)
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
    _require_self_or_admin(payload.salesperson_id, current_user)
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


@router.patch("/{route_id}/reorder", response_model=RouteOut)
def reorder_route(
    route_id: uuid.UUID,
    payload: ReorderRouteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RouteOut:
    route = _load_route(db, route_id)
    if current_user.role != UserRole.ADMIN and route.salesperson_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Route not found")
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
