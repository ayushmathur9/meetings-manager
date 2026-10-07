"""Scheduling/optimization rules (pure logic — no database, no network)."""

from app.services.route_optimizer import DayConfig, StopInput, plan_day, simulate

MIN = 60
HOURS_8 = 8 * 3600  # 08:30 - 16:30


def line_matrix(positions: list[float], *, end: float | None = None, minutes_per_unit: float = 1.0):
    """Points on a line; travel time = |distance| * minutes_per_unit minutes.
    positions[0] is the start; `end` (if given) is appended last."""
    pts = positions + ([end] if end is not None else [])
    return [
        [(int(abs(a - b) * minutes_per_unit * MIN), abs(a - b) * 1000.0) for b in pts]
        for a in pts
    ]


def stops(n: int, duration_min: int = 25, priorities: list[str] | None = None):
    return [
        StopInput(key=f"s{i}", duration_seconds=duration_min * MIN, priority=(priorities or ["medium"] * n)[i])
        for i in range(n)
    ]


def keys(result):
    return [s.key for s in result.simulation.stops]


def test_normal_day_orders_efficiently_and_times_are_consistent():
    # start at 0; stops at 30, 10, 20 -> best order is 10, 20, 30
    matrix = line_matrix([0, 30, 10, 20])
    result = plan_day(stops(3), matrix, DayConfig(day_length_seconds=HOURS_8))
    assert keys(result) == ["s1", "s2", "s0"]
    sim = result.simulation
    first, second, third = sim.stops
    assert first.arrival == 10 * MIN and first.meeting_start == first.arrival
    assert first.meeting_end == first.meeting_start + 25 * MIN
    assert second.arrival == first.meeting_end + 10 * MIN
    assert third.travel_seconds == 10 * MIN
    assert sim.total_travel == 30 * MIN
    assert sim.finish == third.meeting_end  # no fixed end
    assert result.unscheduled == []


def test_buffer_is_added_between_arrival_and_meeting():
    matrix = line_matrix([0, 10])
    result = plan_day(stops(1), matrix, DayConfig(day_length_seconds=HOURS_8, buffer_seconds=5 * MIN))
    stop = result.simulation.stops[0]
    assert stop.arrival == 10 * MIN
    assert stop.meeting_start == 15 * MIN


def test_too_many_meetings_reports_what_does_not_fit():
    # 10 stops * 25 min + travel can't fit in 2 hours
    matrix = line_matrix([0] + [i for i in range(1, 11)])
    result = plan_day(stops(10), matrix, DayConfig(day_length_seconds=2 * 3600))
    scheduled = keys(result)
    assert 0 < len(scheduled) < 10
    assert len(scheduled) + len(result.unscheduled) == 10
    assert all(u.reason == "does_not_fit" for u in result.unscheduled)
    assert result.simulation.finish <= 2 * 3600


def test_allow_overtime_keeps_everything_and_flags_it():
    matrix = line_matrix([0] + [i for i in range(1, 11)])
    result = plan_day(stops(10), matrix, DayConfig(day_length_seconds=2 * 3600, allow_overtime=True))
    assert len(keys(result)) == 10
    assert result.unscheduled == []
    assert result.simulation.overtime > 0
    assert any(s.outside_hours for s in result.simulation.stops)


def test_different_meeting_durations():
    matrix = line_matrix([0, 5, 10])
    s = [StopInput("short", 15 * MIN), StopInput("long", 60 * MIN)]
    sim = plan_day(s, matrix, DayConfig(day_length_seconds=HOURS_8)).simulation
    assert sim.stops[0].meeting_end - sim.stops[0].meeting_start == 15 * MIN
    assert sim.stops[1].meeting_end - sim.stops[1].meeting_start == 60 * MIN


def test_different_working_hours_change_how_many_fit():
    matrix = line_matrix([0, 5, 10, 15, 20])
    short_day = plan_day(stops(4), matrix, DayConfig(day_length_seconds=60 * MIN))
    long_day = plan_day(stops(4), matrix, DayConfig(day_length_seconds=HOURS_8))
    assert len(keys(short_day)) < len(keys(long_day)) == 4


def test_fixed_end_location_counts_return_drive():
    # end back at 0 (same as start)
    matrix = line_matrix([0, 10, 20], end=0)
    sim = plan_day(stops(2), matrix, DayConfig(day_length_seconds=HOURS_8, has_end=True)).simulation
    assert sim.return_travel_seconds == 20 * MIN
    assert sim.finish == sim.stops[-1].meeting_end + 20 * MIN
    assert sim.total_travel == 40 * MIN


def test_fixed_end_influences_order():
    # Start at 0, end at 100: going 10 -> 90 is better than 90 -> 10.
    matrix = line_matrix([0, 90, 10], end=100)
    result = plan_day(stops(2), matrix, DayConfig(day_length_seconds=10 * 3600, has_end=True))
    assert keys(result) == ["s1", "s0"]


def test_return_drive_must_fit_in_working_hours():
    matrix = line_matrix([0, 50], end=0)
    cfg = DayConfig(day_length_seconds=110 * MIN, has_end=True)  # 50 + 25 + 50 = 125 min
    result = plan_day(stops(1), matrix, cfg)
    assert keys(result) == []
    assert result.unscheduled[0].reason == "does_not_fit"


def test_no_fixed_end_finishes_at_last_meeting():
    matrix = line_matrix([0, 10])
    sim = plan_day(stops(1), matrix, DayConfig(day_length_seconds=HOURS_8)).simulation
    assert sim.return_travel_seconds == 0
    assert sim.finish == sim.stops[0].meeting_end


def test_manual_reorder_is_respected():
    matrix = line_matrix([0, 30, 10, 20])
    result = plan_day(stops(3), matrix, DayConfig(day_length_seconds=HOURS_8), optimize=False, initial_order=[1, 2, 3])
    assert keys(result) == ["s0", "s1", "s2"]
    # Manual (inefficient) order costs more driving than the optimized one.
    optimized = plan_day(stops(3), matrix, DayConfig(day_length_seconds=HOURS_8))
    assert result.simulation.total_travel > optimized.simulation.total_travel


def test_priority_decides_who_is_left_out_not_the_order():
    # Room for only 2 of 3 meetings; the low-priority one should be dropped
    # even though it is the closest.
    matrix = line_matrix([0, 5, 10, 15])
    cfg = DayConfig(day_length_seconds=70 * MIN)
    result = plan_day(stops(3, priorities=["low", "high", "high"]), matrix, cfg)
    assert keys(result) == ["s1", "s2"]
    assert [u.key for u in result.unscheduled] == ["s0"]


def test_high_priority_does_not_wreck_efficient_order():
    matrix = line_matrix([0, 30, 10, 20])
    result = plan_day(stops(3, priorities=["high", "low", "low"]), matrix, DayConfig(day_length_seconds=HOURS_8))
    assert keys(result) == ["s1", "s2", "s0"]


def test_committed_meeting_time_is_kept_and_waited_for():
    matrix = line_matrix([0, 10, 20])
    s = [StopInput("fixed", 25 * MIN, fixed_start=120 * MIN), StopInput("free", 25 * MIN)]
    sim = plan_day(s, matrix, DayConfig(day_length_seconds=HOURS_8)).simulation
    fixed = next(x for x in sim.stops if x.key == "fixed")
    assert fixed.meeting_start == 120 * MIN
    assert fixed.late_seconds == 0


def test_unreachable_stop_is_reported():
    matrix = line_matrix([0, 10, 20])
    for i in range(3):
        if i != 2:
            matrix[i][2] = None
            matrix[2][i] = None
    result = plan_day(stops(2), matrix, DayConfig(day_length_seconds=HOURS_8))
    assert keys(result) == ["s0"]
    assert result.unscheduled[0].reason == "unreachable"


def test_external_seed_is_credited_when_optimal():
    matrix = line_matrix([0, 30, 10, 20])
    result = plan_day(stops(3), matrix, DayConfig(day_length_seconds=HOURS_8), seeds={"geoapify": [2, 3, 1]})
    assert result.used_seed == "geoapify"


def test_larger_route_uses_local_search():
    positions = [0] + [((i * 37) % 23) + 1 for i in range(12)]
    matrix = line_matrix(positions)
    result = plan_day(stops(12, duration_min=15), matrix, DayConfig(day_length_seconds=10 * 3600))
    sim = result.simulation
    assert len(sim.stops) == 12
    # On a line, the optimal drive is to the farthest point and no back-tracking.
    assert sim.total_travel == max(positions) * MIN


def test_simulate_empty_order():
    sim = simulate([], [], [[(0, 0.0)]], DayConfig(day_length_seconds=HOURS_8))
    assert sim.stops == [] and sim.finish == 0


def test_meetings_start_on_whole_minutes():
    matrix = [[(0, 0.0), (125, 900.0)], [(125, 900.0), (0, 0.0)]]  # 2 min 5 s drive
    stop = plan_day(stops(1), matrix, DayConfig(day_length_seconds=HOURS_8)).simulation.stops[0]
    assert stop.arrival == 125
    assert stop.meeting_start == 180
    assert stop.meeting_end % 60 == 0
