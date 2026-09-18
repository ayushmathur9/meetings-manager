"""Daily route generation and optimization.

Uses a practical nearest-neighbor construction followed by a 2-opt local
search over real driving travel times from the LocationProvider's distance
matrix, respecting working hours and a travel buffer between meetings. This
is intentionally not ML-based (spec: "does not need advanced AI") — it just
needs to produce a realistic, low-backtracking sequence.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.meeting import Meeting
from app.models.route import Route, RouteStop
from app.providers.location.base import LocationProvider
from app.schemas.route import GenerateRouteRequest, NamedLocation


class RouteService:
    def __init__(self, db: Session, location_provider: LocationProvider) -> None:
        self.db = db
        self.location_provider = location_provider

    def generate_route(
        self, payload: GenerateRouteRequest, *, fixed_meeting_ids: set[uuid.UUID] | None = None
    ) -> Route:
        """Build/rebuild a route from `payload.meeting_ids`.

        Meetings whose id is in `fixed_meeting_ids` already have a real,
        user- or planner-committed `start_time` (e.g. a previously scheduled
        meeting) and must keep that exact time — the optimizer only chooses
        where they fall in the visiting order, and the remaining meetings are
        scheduled around them, not the other way around.
        """
        fixed_meeting_ids = fixed_meeting_ids or set()
        meetings = (
            self.db.query(Meeting)
            .options(joinedload(Meeting.location), joinedload(Meeting.company))
            .filter(Meeting.id.in_(payload.meeting_ids))
            .all()
        )
        meetings = [m for m in meetings if m.location and m.location.latitude is not None]
        if not meetings:
            raise ValueError("None of the selected meetings have a verified location")

        points = [(payload.start_location.latitude, payload.start_location.longitude)]
        points += [(m.location.latitude, m.location.longitude) for m in meetings]
        if payload.end_location:
            points.append((payload.end_location.latitude, payload.end_location.longitude))

        matrix = self.location_provider.calculate_travel_time_matrix(points, points)

        order = self._nearest_neighbor_order(matrix, len(meetings))
        order = self._two_opt(order, matrix)

        fixed_order_indices = {i for i in order if meetings[i - 1].id in fixed_meeting_ids}
        if fixed_order_indices:
            order = self._reorder_respecting_fixed_times(order, meetings, fixed_order_indices)

        ordered_meetings = [meetings[i - 1] for i in order]

        existing_route = (
            self.db.query(Route)
            .filter(Route.salesperson_id == payload.salesperson_id, Route.date == payload.date)
            .first()
        )
        if existing_route:
            self.db.query(RouteStop).filter(RouteStop.route_id == existing_route.id).delete()
            route = existing_route
        else:
            route = Route(salesperson_id=payload.salesperson_id, date=payload.date)
            self.db.add(route)

        # A meeting can only be a stop on one route at a time (route_stops.meeting_id
        # is unique). If any selected meeting was previously routed elsewhere (e.g. a
        # different date), drop that stale stop so re-routing it here doesn't collide.
        meeting_ids = [m.id for m in meetings]
        self.db.query(RouteStop).filter(RouteStop.meeting_id.in_(meeting_ids)).delete(
            synchronize_session=False
        )

        route.start_location = payload.start_location.model_dump()
        route.end_location = payload.end_location.model_dump() if payload.end_location else None

        current_time = datetime.combine(payload.date, payload.working_hours_start)
        total_distance = 0.0
        total_duration = 0
        stops = []

        prev_index = 0  # index 0 in `points`/`matrix` is the start location
        for seq, meeting_order_index in enumerate(order, start=1):
            meeting = meetings[meeting_order_index - 1]
            travel = matrix[prev_index][meeting_order_index]
            travel_seconds = travel.duration_seconds if travel else 0
            travel_meters = travel.distance_meters if travel else 0.0

            current_time += timedelta(seconds=travel_seconds)
            if meeting.id in fixed_meeting_ids:
                # Never move a meeting that's already committed to a time —
                # arrive whenever travel puts us there, but the meeting itself
                # starts (and ends) exactly when it was scheduled.
                fixed_start = datetime.combine(payload.date, meeting.start_time)
                arrival_time = min(current_time, fixed_start).time()
                current_time = max(current_time, fixed_start)
                current_time += timedelta(minutes=meeting.duration_minutes)
            else:
                arrival_time = current_time.time()
                current_time += timedelta(minutes=meeting.duration_minutes)
            departure_time = current_time.time()
            current_time += timedelta(minutes=payload.travel_buffer_minutes)

            stop = RouteStop(
                route=route,
                meeting_id=meeting.id,
                sequence=seq,
                arrival_time=arrival_time,
                departure_time=departure_time,
                travel_time_seconds=travel_seconds,
                distance_meters=travel_meters,
            )
            stops.append(stop)
            total_distance += travel_meters
            total_duration += travel_seconds
            prev_index = meeting_order_index

        if payload.end_location:
            end_index = len(points) - 1
            final_travel = matrix[prev_index][end_index]
            if final_travel:
                total_distance += final_travel.distance_meters
                total_duration += final_travel.duration_seconds

        route.stops = stops
        route.estimated_distance_meters = total_distance
        route.estimated_duration_seconds = total_duration
        self.db.flush()
        return route

    def _reorder_respecting_fixed_times(
        self, order: list[int], meetings: list[Meeting], fixed_order_indices: set[int]
    ) -> list[int]:
        """Stable-sort a 2-opt order so fixed-time meetings appear in
        chronological order relative to each other, while movable meetings
        keep their position relative to the nearest fixed meetings around
        them (a minimal-disruption fix-up, not a full re-optimization).
        """
        fixed_sorted = sorted(fixed_order_indices, key=lambda i: meetings[i - 1].start_time)
        fixed_rank = {idx: rank for rank, idx in enumerate(fixed_sorted)}

        segments: list[list[int]] = [[] for _ in range(len(fixed_sorted) + 1)]
        seg = 0
        for idx in order:
            if idx in fixed_rank:
                seg = fixed_rank[idx] + 1
                segments[fixed_rank[idx]].append(idx)
            else:
                segments[seg].append(idx)

        result: list[int] = []
        for seg_items in segments:
            result.extend(seg_items)
        return result

    def _nearest_neighbor_order(self, matrix, n_meetings: int) -> list[int]:
        unvisited = set(range(1, n_meetings + 1))
        order = []
        current = 0
        while unvisited:
            best = min(
                unvisited,
                key=lambda i: matrix[current][i].duration_seconds if matrix[current][i] else float("inf"),
            )
            order.append(best)
            unvisited.remove(best)
            current = best
        return order

    def _two_opt(self, order: list[int], matrix) -> list[int]:
        def route_cost(seq: list[int]) -> float:
            cost = 0.0
            prev = 0
            for idx in seq:
                edge = matrix[prev][idx]
                cost += edge.duration_seconds if edge else 1e9
                prev = idx
            return cost

        best = order[:]
        best_cost = route_cost(best)
        improved = True
        while improved:
            improved = False
            for i in range(len(best) - 1):
                for j in range(i + 1, len(best)):
                    candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                    candidate_cost = route_cost(candidate)
                    if candidate_cost < best_cost:
                        best, best_cost = candidate, candidate_cost
                        improved = True
        return best

    def get_route_for_day(self, salesperson_id: uuid.UUID, date) -> Route | None:
        return (
            self.db.query(Route)
            .filter(Route.salesperson_id == salesperson_id, Route.date == date)
            .first()
        )

    def reorder_route(self, route: Route, ordered_meeting_ids: list[uuid.UUID]) -> Route:
        stops_by_meeting = {s.meeting_id: s for s in route.stops}
        points_cache = {}
        for stop in route.stops:
            meeting = self.db.get(Meeting, stop.meeting_id)
            if meeting and meeting.location:
                points_cache[stop.meeting_id] = (meeting.location.latitude, meeting.location.longitude)

        start = route.start_location
        prev_point = (start["latitude"], start["longitude"])
        current_time = datetime.combine(route.date, datetime.min.time().replace(hour=9))

        total_distance = 0.0
        total_duration = 0

        for seq, meeting_id in enumerate(ordered_meeting_ids, start=1):
            stop = stops_by_meeting[meeting_id]
            point = points_cache.get(meeting_id)
            if point:
                travel = self.location_provider.calculate_travel_time(prev_point, point)
                stop.travel_time_seconds = travel.duration_seconds
                stop.distance_meters = travel.distance_meters
                current_time += timedelta(seconds=travel.duration_seconds)
                stop.arrival_time = current_time.time()
                meeting = self.db.get(Meeting, meeting_id)
                current_time += timedelta(minutes=meeting.duration_minutes if meeting else 25)
                stop.departure_time = current_time.time()
                total_distance += travel.distance_meters
                total_duration += travel.duration_seconds
                prev_point = point
            stop.sequence = seq

        route.estimated_distance_meters = total_distance
        route.estimated_duration_seconds = total_duration
        self.db.flush()
        return route
