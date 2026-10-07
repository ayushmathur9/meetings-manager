"""Sales-day scheduling + stop-order optimization (pure logic, no I/O).

Inputs are a travel matrix (from Geoapify, or another road-network provider)
and a list of meetings; output is a timed schedule. Rules are applied in this
order of importance:

  1. Hard constraints   — unreachable stops can't be scheduled; meetings with
                          a committed time never move.
  2. Working hours      — every meeting (and the drive to a fixed end
                          location) must finish inside the window, unless the
                          caller explicitly allows overtime.
  3. Fixed start / end  — the day starts at `start`; if an end location is
                          set, the day finishes there.
  4. Meeting duration   — per-stop durations (+ arrival buffer) are honoured.
  5. Priority           — when not everything fits, lower-priority stops are
                          left out first; priority never re-orders a feasible
                          route at the expense of efficiency.
  6. Route efficiency   — among feasible orders, minimize end-of-day time, then
                          total driving.

Stops that can't be scheduled are returned in `unscheduled` with a reason —
never silently dropped.

Matrix layout: index 0 = start, 1..n = stops (same order as `stops`),
n + 1 = end location (only when `has_end`). Each cell is
(duration_seconds, distance_meters) or None when unreachable. All times are
seconds relative to the start of the working day.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
BRUTE_FORCE_MAX_STOPS = 7

Cell = tuple[int, float] | None
Matrix = list[list[Cell]]


@dataclass
class StopInput:
    key: str
    duration_seconds: int
    priority: str = "medium"
    fixed_start: int | None = None  # committed meeting start, relative seconds


@dataclass
class DayConfig:
    day_length_seconds: int  # working end - working start
    buffer_seconds: int = 0  # parking/check-in time between arriving and meeting
    has_end: bool = False
    allow_overtime: bool = False


@dataclass
class ScheduledStop:
    index: int  # 1-based matrix index
    key: str
    travel_seconds: int
    distance_meters: float
    arrival: int
    meeting_start: int
    meeting_end: int
    wait_seconds: int
    late_seconds: int  # arrival after a committed meeting time
    outside_hours: bool


@dataclass
class Simulation:
    stops: list[ScheduledStop]
    unreachable: list[int]
    return_travel_seconds: int = 0
    return_distance_meters: float = 0.0
    finish: int = 0  # departure from last stop, or arrival at end location
    total_travel: int = 0
    total_distance: float = 0.0
    lateness: int = 0
    overtime: int = 0

    def cost(self) -> tuple:
        return (len(self.unreachable), self.lateness, self.overtime, self.finish, self.total_travel)


@dataclass
class UnscheduledStop:
    key: str
    reason: str  # "unreachable" | "does_not_fit"


@dataclass
class PlanResult:
    simulation: Simulation
    unscheduled: list[UnscheduledStop] = field(default_factory=list)
    used_seed: str | None = None  # name of the seed order that won, if any


# --------------------------------------------------------------------------- simulation


def simulate(order: list[int], stops: list[StopInput], matrix: Matrix, config: DayConfig) -> Simulation:
    sim = Simulation(stops=[], unreachable=[])
    t = 0
    prev = 0
    for idx in order:
        cell = matrix[prev][idx]
        if cell is None:
            sim.unreachable.append(idx)
            continue
        travel, dist = cell
        stop = stops[idx - 1]
        arrival = t + travel
        # Meetings start on a whole minute (calendars don't book 9:33:42);
        # the few seconds of slack are absorbed before the meeting starts.
        ready = -(-(arrival + config.buffer_seconds) // 60) * 60
        start = ready
        wait = late = 0
        if stop.fixed_start is not None:
            if ready <= stop.fixed_start:
                wait = stop.fixed_start - ready
                start = stop.fixed_start
            else:
                late = ready - stop.fixed_start
                start = ready
        end = start + stop.duration_seconds
        outside = end > config.day_length_seconds
        sim.stops.append(
            ScheduledStop(idx, stop.key, travel, dist, arrival, start, end, wait, late, outside)
        )
        sim.total_travel += travel
        sim.total_distance += dist
        sim.lateness += late
        t = end
        prev = idx

    sim.finish = t
    if config.has_end:
        end_idx = len(stops) + 1
        cell = matrix[prev][end_idx]
        if cell is not None:
            sim.return_travel_seconds, sim.return_distance_meters = cell
            sim.total_travel += cell[0]
            sim.total_distance += cell[1]
            sim.finish = t + cell[0]
        elif sim.stops:
            # Can't get from the last stop to the end location: treat the last
            # stop as unreachable so the optimizer tries another ordering.
            sim.unreachable.append(prev)
    sim.overtime = max(0, sim.finish - config.day_length_seconds)
    return sim


# --------------------------------------------------------------------------- ordering


def _nearest_neighbor(active: list[int], matrix: Matrix) -> list[int]:
    remaining = set(active)
    order: list[int] = []
    current = 0
    while remaining:
        best = min(
            remaining,
            key=lambda i: (matrix[current][i][0] if matrix[current][i] is not None else float("inf"), i),
        )
        order.append(best)
        remaining.remove(best)
        current = best
    return order


def _local_search(order: list[int], cost) -> list[int]:
    """2-opt + or-opt (single-stop relocation) until no improvement."""
    best = order[:]
    best_cost = cost(best)
    improved = True
    while improved:
        improved = False
        n = len(best)
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                c = cost(candidate)
                if c < best_cost:
                    best, best_cost, improved = candidate, c, True
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                candidate = best[:i] + best[i + 1 :]
                candidate.insert(j, best[i])
                c = cost(candidate)
                if c < best_cost:
                    best, best_cost, improved = candidate, c, True
    return best


def best_order(
    active: list[int],
    stops: list[StopInput],
    matrix: Matrix,
    config: DayConfig,
    seeds: dict[str, list[int]] | None = None,
) -> tuple[list[int], str | None]:
    """Best visiting order for `active` stops. Returns (order, winning seed name)."""
    if len(active) <= 1:
        return active[:], None

    def cost(order: list[int]) -> tuple:
        return simulate(order, stops, matrix, config).cost()

    if len(active) <= BRUTE_FORCE_MAX_STOPS:
        best = min((list(p) for p in itertools.permutations(active)), key=cost)
        winner = None
        for name, seed in (seeds or {}).items():
            filtered = [i for i in seed if i in active]
            if len(filtered) == len(active) and cost(filtered) <= cost(best):
                winner = name
                best = filtered
        return best, winner

    candidates: dict[str | None, list[int]] = {None: _local_search(_nearest_neighbor(active, matrix), cost)}
    for name, seed in (seeds or {}).items():
        filtered = [i for i in seed if i in active]
        filtered += [i for i in active if i not in filtered]
        candidates[name] = _local_search(filtered, cost)
    # Prefer an external seed on ties so its contribution is credited.
    name, order = min(candidates.items(), key=lambda kv: (cost(kv[1]), kv[0] is None))
    return order, name


# --------------------------------------------------------------------------- planning


def plan_day(
    stops: list[StopInput],
    matrix: Matrix,
    config: DayConfig,
    *,
    optimize: bool = True,
    initial_order: list[int] | None = None,
    seeds: dict[str, list[int]] | None = None,
) -> PlanResult:
    """Order (optionally) and schedule `stops`, leaving out — and reporting —
    whatever can't be reached or can't fit in working hours.

    `initial_order` (1-based matrix indices) is the user's manual order; with
    `optimize=False` it is kept exactly, minus any stops that don't fit.
    """
    active = list(initial_order) if initial_order else list(range(1, len(stops) + 1))
    unscheduled: list[UnscheduledStop] = []
    used_seed: str | None = None

    # Stops nobody can drive to/from at all are removed up-front.
    for idx in list(active):
        if matrix[0][idx] is None and all(matrix[j][idx] is None for j in active if j != idx):
            active.remove(idx)
            unscheduled.append(UnscheduledStop(stops[idx - 1].key, "unreachable"))

    while True:
        if optimize:
            order, used_seed = best_order(active, stops, matrix, config, seeds)
        else:
            order = active[:]
        sim = simulate(order, stops, matrix, config)

        if sim.unreachable:
            for idx in sim.unreachable:
                if idx in active:
                    active.remove(idx)
                    unscheduled.append(UnscheduledStop(stops[idx - 1].key, "unreachable"))
            continue

        if config.allow_overtime or sim.overtime == 0 or not active:
            return PlanResult(sim, unscheduled, used_seed)

        victim = _choose_removal(order, stops, matrix, config)
        active.remove(victim)
        unscheduled.append(UnscheduledStop(stops[victim - 1].key, "does_not_fit"))


def _choose_removal(order: list[int], stops: list[StopInput], matrix: Matrix, config: DayConfig) -> int:
    """Lowest priority first (committed-time meetings last); within the same
    priority, drop the stop whose removal saves the most time."""

    def rank(idx: int) -> int:
        stop = stops[idx - 1]
        return 99 if stop.fixed_start is not None else PRIORITY_RANK.get(stop.priority, 2)

    lowest = min(rank(i) for i in order)
    pool = [i for i in order if rank(i) == lowest]
    return min(
        pool,
        key=lambda i: (simulate([j for j in order if j != i], stops, matrix, config).finish, -order.index(i)),
    )
