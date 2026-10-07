"""Route planner API: PostGIS radius filtering, permissions, planning,
saving/reopening, reordering and recalculation. Geoapify is faked."""

from datetime import date
from math import asin, cos, radians, sin, sqrt

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import text

from app.models.company import Company
from app.models.location import Location, LocationSource, VerificationStatus
from app.models.meeting import Meeting
from app.models.prospect import Prospect, ProspectPriority
from app.models.route import Route
from app.providers.location.base import TravelTimeResult
from app.services import sales_day_planner
from app.services.geoapify import PlannerResult, RouteResult

GIG_EAST = {"name": "Gig East Exchange", "address": "127 Goldsboro St S, Wilson, NC", "latitude": 35.7213, "longitude": -77.9155}
DAY = "2026-10-12"


def _haversine(a, b):
    lat1, lng1, lat2, lng2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


class FakeGeoapify:
    """Deterministic stand-in: ~40 km/h over 1.3x straight-line distance."""

    is_configured = True

    def __init__(self):
        self.matrix_calls = []
        self.route_calls = []

    def get_route_matrix(self, sources, targets, mode="drive"):
        self.matrix_calls.append(list(sources))
        rows = []
        for o in sources:
            row = []
            for d in targets:
                meters = _haversine(o, d) * 1.3
                row.append(TravelTimeResult(int(meters / 11), meters, o, d))
            rows.append(row)
        return rows

    def get_route(self, waypoints, mode="drive"):
        self.route_calls.append(list(waypoints))
        return RouteResult(1000, 100, [], [[[lng, lat] for lat, lng in waypoints]])

    def optimize_route(self, start, jobs, **kwargs):
        return PlannerResult(order=list(range(len(jobs))))


@pytest.fixture
def fake_geo(monkeypatch):
    fake = FakeGeoapify()
    monkeypatch.setattr(sales_day_planner, "get_geoapify_client", lambda: fake)
    return fake


def add_company(db, name, lat=None, lng=None, *, assigned_to=None, priority=ProspectPriority.MEDIUM, address="1 Main St"):
    company = Company(name=name, normalized_name=name.lower(), industry="Healthcare")
    db.add(company)
    db.flush()
    location = Location(
        company_id=company.id,
        is_primary=True,
        address_line_1=address,
        city="Wilson",
        state="NC",
        latitude=lat,
        longitude=lng,
        geom=from_shape(Point(lng, lat), srid=4326) if lat is not None else None,
        source=LocationSource.GEOCODED if lat is not None else LocationSource.NEEDS_VERIFICATION,
        verification_status=VerificationStatus.VERIFIED if lat is not None else VerificationStatus.NEEDS_REVIEW,
    )
    db.add(location)
    db.add(Prospect(company_id=company.id, assigned_user_id=assigned_to.id if assigned_to else None, priority=priority))
    db.commit()
    return company


@pytest.fixture
def wilson(db, sales_user, other_sales_user):
    """Realistic Wilson, NC healthcare prospects."""
    return {
        "derm": add_company(db, "Eastern Dermatology", 35.7305, -77.9515, assigned_to=sales_user, priority=ProspectPriority.HIGH),
        "wmg": add_company(db, "Wilson Medical Group", 35.7675, -77.9378, assigned_to=sales_user, priority=ProspectPriority.HIGH),
        "peds": add_company(db, "Eastern Carolina Pediatrics", 35.7234, -77.9430, assigned_to=sales_user),
        "chiro": add_company(db, "Cato Family Chiropractic", 35.7514, -77.9289, assigned_to=sales_user, priority=ProspectPriority.LOW),
        # ~85 miles away (Kelly, NC)
        "far": add_company(db, "Kelly Chiropractic Center", 34.4666, -78.3243, assigned_to=sales_user),
        "nocoords": add_company(db, "Polley Clinic of Dermatology", assigned_to=sales_user, address="1806 Glendale Dr SW"),
        "theirs": add_company(db, "Freedom Family Medicine", 35.7510, -77.9615, assigned_to=other_sales_user),
    }


def plan_payload(company_ids, **overrides):
    payload = {
        "date": DAY,
        "start_location": GIG_EAST,
        "working_hours_start": "08:30:00",
        "working_hours_end": "16:30:00",
        "meeting_duration_minutes": 25,
        "radius_miles": 20,
        "stops": [{"company_id": str(c)} for c in company_ids],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- radius (PostGIS)


def test_radius_inside_outside_missing(sales_client, wilson):
    res = sales_client.post("/routes/preview", json={"date": DAY, "start_location": GIG_EAST, "radius_miles": 20})
    assert res.status_code == 200, res.text
    body = res.json()
    by_name = {c["company_name"]: c for c in body["candidates"]}
    assert by_name["Eastern Dermatology"]["radius_status"] == "inside"
    assert by_name["Kelly Chiropractic Center"]["radius_status"] == "outside"
    assert by_name["Kelly Chiropractic Center"]["distance_miles"] > 20
    assert by_name["Polley Clinic of Dermatology"]["radius_status"] == "missing_coordinates"
    assert by_name["Polley Clinic of Dermatology"]["distance_miles"] is None
    # Only the salesperson's own prospects
    assert "Freedom Family Medicine" not in by_name
    assert (body["inside_count"], body["outside_count"], body["missing_count"]) == (4, 1, 1)
    # Inside first, nearest first
    statuses = [c["radius_status"] for c in body["candidates"]]
    assert statuses == sorted(statuses, key=["inside", "outside", "missing_coordinates"].index)
    assert by_name["Eastern Dermatology"]["priority"] == "high"


def test_radius_boundary_condition(db, sales_client, wilson):
    distance_m = db.execute(
        text(
            "SELECT ST_Distance(ST_SetSRID(ST_MakePoint(:lng1,:lat1),4326)::geography,"
            " ST_SetSRID(ST_MakePoint(:lng2,:lat2),4326)::geography)"
        ),
        {"lng1": -77.9515, "lat1": 35.7305, "lng2": GIG_EAST["longitude"], "lat2": GIG_EAST["latitude"]},
    ).scalar()
    exact_miles = distance_m / 1609.344

    def status_at(radius):
        res = sales_client.post("/routes/preview", json={"start_location": GIG_EAST, "radius_miles": radius})
        return {c["company_name"]: c for c in res.json()["candidates"]}["Eastern Dermatology"]["radius_status"]

    assert status_at(exact_miles * 1.0001) == "inside"
    assert status_at(exact_miles * 0.9999) == "outside"


# --------------------------------------------------------------------------- planning


def test_optimize_route_end_to_end(sales_client, wilson, fake_geo):
    ids = [wilson[k].id for k in ("wmg", "derm", "peds", "chiro")]
    res = sales_client.post("/routes/optimize", json=plan_payload(ids))
    assert res.status_code == 200, res.text
    plan = res.json()
    assert plan["scheduled_count"] == 4 and plan["unscheduled"] == []
    assert plan["routing_engine"] == "geoapify"
    assert plan["optimization_engine"] in ("local", "geoapify_route_planner")
    stops = plan["stops"]
    assert [s["sequence"] for s in stops] == [1, 2, 3, 4]
    assert stops[0]["arrival_time"] > "08:30:00"
    for a, b in zip(stops, stops[1:]):
        assert b["arrival_time"] >= a["departure_time"]
    assert all(s["meeting_end"] > s["meeting_start"] for s in stops)
    assert plan["total_meeting_seconds"] == 4 * 25 * 60
    assert plan["config"]["end_mode"] == "none"  # day ends at the last meeting
    assert plan["return_travel_seconds"] == 0
    assert plan["day_finish"] == stops[-1]["meeting_end"]
    assert plan["total_distance_meters"] > 0 and plan["total_driving_seconds"] > 0
    assert plan["geometry"]
    # One matrix call containing start + 4 stops; nothing else sent out.
    assert len(fake_geo.matrix_calls) == 1 and len(fake_geo.matrix_calls[0]) == 5


def test_missing_coordinates_lists_affected_companies(sales_client, wilson, fake_geo):
    res = sales_client.post("/routes/optimize", json=plan_payload([wilson["derm"].id, wilson["nocoords"].id]))
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "missing_coordinates"
    assert "1 selected prospect does not have valid coordinates" in detail["message"]
    assert [c["company_name"] for c in detail["companies"]] == ["Polley Clinic of Dermatology"]
    assert fake_geo.matrix_calls == []  # never reached Geoapify


def test_too_many_meetings_warning(sales_client, wilson, fake_geo):
    ids = [wilson[k].id for k in ("wmg", "derm", "peds", "chiro")]
    res = sales_client.post(
        "/routes/optimize",
        json=plan_payload(ids, working_hours_start="08:30:00", working_hours_end="09:45:00"),
    )
    plan = res.json()
    assert 0 < plan["scheduled_count"] < 4
    assert plan["warnings"][0].startswith(f"4 meetings selected, but only {plan['scheduled_count']} fit")
    assert {u["reason"] for u in plan["unscheduled"]} == {"does_not_fit"}
    # The LOW priority prospect is the first to be left out.
    assert "Cato Family Chiropractic" in [u["company_name"] for u in plan["unscheduled"]]


def test_outside_radius_selection_is_left_out_and_reported(sales_client, wilson, fake_geo):
    res = sales_client.post(
        "/routes/optimize",
        json=plan_payload([wilson["derm"].id, wilson["far"].id], working_hours_end="20:00:00"),
    )
    plan = res.json()
    assert [s["company_name"] for s in plan["stops"]] == ["Eastern Dermatology"]
    assert plan["unscheduled"][0]["company_name"] == "Kelly Chiropractic Center"
    assert plan["unscheduled"][0]["reason"] == "outside_radius"
    assert plan["selected_count"] == 2
    assert any("outside the 20-mile radius" in w for w in plan["warnings"])
    # The far prospect was never sent to Geoapify.
    assert len(fake_geo.matrix_calls[0]) == 2


def test_all_outside_radius_is_a_clear_error(sales_client, wilson, fake_geo):
    res = sales_client.post("/routes/optimize", json=plan_payload([wilson["far"].id]))
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "all_outside_radius"
    assert fake_geo.matrix_calls == []


class _IsolatedPointGeo(FakeGeoapify):
    """Fake where one coordinate (a mountain peak, say) has no road access."""

    def __init__(self, isolated):
        super().__init__()
        self.isolated = isolated

    def get_route_matrix(self, sources, targets, mode="drive"):
        rows = super().get_route_matrix(sources, targets, mode)
        for i, o in enumerate(sources):
            for j, d in enumerate(targets):
                if (o == self.isolated) != (d == self.isolated):
                    rows[i][j] = None
        return rows


def test_unroutable_start_is_reported_once_not_blamed_on_every_stop(sales_client, wilson, monkeypatch):
    peak = {"name": "Little Sam Knob", "latitude": 35.7240, "longitude": -77.9200}
    monkeypatch.setattr(sales_day_planner, "get_geoapify_client", lambda: _IsolatedPointGeo((35.724, -77.92)))
    res = sales_client.post(
        "/routes/optimize", json=plan_payload([wilson["derm"].id, wilson["peds"].id], start_location=peak)
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "start_unreachable"


def test_unroutable_end_on_legacy_route_is_reported(sales_client, wilson, monkeypatch):
    peak = {"name": "Little Sam Knob", "latitude": 35.3208588, "longitude": -82.8966696}
    monkeypatch.setattr(sales_day_planner, "get_geoapify_client", lambda: _IsolatedPointGeo((35.3208588, -82.8966696)))
    res = sales_client.post(
        "/routes/optimize",
        json=plan_payload([wilson["derm"].id, wilson["peds"].id], end_mode="custom", end_location=peak),
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "end_unreachable"


def test_invalid_start_coordinates(sales_client, wilson, fake_geo):
    bad = {**GIG_EAST, "latitude": 0, "longitude": 0}
    res = sales_client.post("/routes/optimize", json=plan_payload([wilson["derm"].id], start_location=bad))
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_coordinates"


def test_too_many_stops(sales_client, db, sales_user, fake_geo):
    ids = [add_company(db, f"Clinic {i}", 35.72 + i * 0.001, -77.91, assigned_to=sales_user).id for i in range(26)]
    res = sales_client.post("/routes/optimize", json=plan_payload(ids))
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "too_many_stops"


def test_routing_not_configured_gives_clear_error(sales_client, wilson, monkeypatch):
    class Unconfigured(FakeGeoapify):
        is_configured = False

    monkeypatch.setattr(sales_day_planner, "get_geoapify_client", lambda: Unconfigured())
    res = sales_client.post("/routes/optimize", json=plan_payload([wilson["derm"].id]))
    # No Geoapify key and no other road-network provider: never fall back to straight lines.
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "routing_not_configured"


# --------------------------------------------------------------------------- save / load / reorder


def test_save_reopen_reorder_recalculate(db, sales_client, sales_user, wilson, fake_geo):
    ids = [wilson[k].id for k in ("wmg", "derm", "peds")]
    plan = sales_client.post("/routes/optimize", json=plan_payload(ids)).json()

    saved = sales_client.post("/routes", json={"plan": plan})
    assert saved.status_code == 201, saved.text
    route = saved.json()
    assert [s["company_id"] for s in route["stops"]] == [s["company_id"] for s in plan["stops"]]
    assert route["geometry"] == plan["geometry"]
    assert route["total_distance_meters"] == plan["total_distance_meters"]
    assert route["is_stale"] is False
    # Meetings were created for the day at the planned times
    meetings = db.query(Meeting).filter(Meeting.salesperson_id == sales_user.id, Meeting.date == date(2026, 10, 12)).all()
    assert len(meetings) == 3
    assert {m.start_time.isoformat() for m in meetings} == {s["meeting_start"] for s in plan["stops"]}

    # Reopen
    reopened = sales_client.get(f"/routes/{route['id']}").json()
    assert reopened["stops"] == route["stops"]
    listed = sales_client.get("/routes").json()
    assert [r["id"] for r in listed] == [route["id"]]
    assert listed[0]["stop_count"] == 3

    # Manual reorder: reverse, recalculate without optimizing
    reversed_ids = [s["company_id"] for s in reversed(plan["stops"])]
    manual = sales_client.post(
        "/routes/optimize",
        json={**plan_payload(reversed_ids), "optimize": False},
    ).json()
    assert [s["company_id"] for s in manual["stops"]] == reversed_ids
    assert manual["optimization_engine"] == "manual"

    # Remove a stop and save over the existing route
    manual_two = sales_client.post(
        "/routes/optimize", json={**plan_payload(reversed_ids[:2]), "optimize": False}
    ).json()
    updated = sales_client.patch(f"/routes/{route['id']}", json={"plan": manual_two, "status": "confirmed"})
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["stops"]) == 2 and updated.json()["status"] == "confirmed"
    remaining = db.query(Meeting).filter(Meeting.salesperson_id == sales_user.id, Meeting.date == date(2026, 10, 12)).count()
    assert remaining == 2  # the dropped stop's provisional meeting was removed

    # Saved route recalculates against current locations, without saving
    recalculated = sales_client.post(f"/routes/{route['id']}/recalculate", json={"optimize": False})
    assert recalculated.status_code == 200, recalculated.text
    assert [s["company_id"] for s in recalculated.json()["stops"]] == reversed_ids[:2]

    # Delete
    assert sales_client.delete(f"/routes/{route['id']}").status_code == 204
    assert db.query(Route).count() == 0
    assert db.query(Meeting).filter(Meeting.salesperson_id == sales_user.id).count() == 0


def test_saved_route_flags_changed_company_location(db, sales_client, wilson, fake_geo):
    plan = sales_client.post("/routes/optimize", json=plan_payload([wilson["derm"].id])).json()
    route = sales_client.post("/routes", json={"plan": plan}).json()
    location = db.query(Location).filter(Location.company_id == wilson["derm"].id).one()
    location.latitude += 0.01
    db.flush()
    reopened = sales_client.get(f"/routes/{route['id']}").json()
    assert reopened["is_stale"] is True
    assert reopened["stops"][0]["location_changed"] is True
    # The saved plan itself was not silently changed
    assert reopened["stops"][0]["latitude"] == plan["stops"][0]["latitude"]


def test_existing_fixed_meeting_time_is_respected(db, sales_client, sales_user, wilson, fake_geo):
    from datetime import time

    db.add(
        Meeting(
            company_id=wilson["wmg"].id, salesperson_id=sales_user.id, date=date(2026, 10, 12),
            start_time=time(11, 0), end_time=time(11, 30), duration_minutes=30, created_by_id=sales_user.id,
        )
    )
    db.flush()
    plan = sales_client.post("/routes/optimize", json=plan_payload([wilson["wmg"].id, wilson["derm"].id])).json()
    fixed = next(s for s in plan["stops"] if s["company_name"] == "Wilson Medical Group")
    assert fixed["is_fixed_time"] is True
    assert fixed["meeting_start"] == "11:00:00"
    assert fixed["duration_minutes"] == 30


# --------------------------------------------------------------------------- permissions


def test_unauthenticated_is_rejected(anon_client):
    assert anon_client.get("/routes").status_code == 401
    assert anon_client.post("/routes/preview", json={"start_location": GIG_EAST}).status_code == 401


def test_salesperson_cannot_plan_with_other_peoples_prospects(sales_client, wilson, fake_geo):
    res = sales_client.post("/routes/optimize", json=plan_payload([wilson["theirs"].id]))
    assert res.status_code == 403
    assert res.json()["detail"]["companies"][0]["company_name"] == "Freedom Family Medicine"


def test_salesperson_cannot_plan_for_someone_else(sales_client, other_sales_user, wilson, fake_geo):
    res = sales_client.post(
        "/routes/optimize", json={**plan_payload([wilson["derm"].id]), "salesperson_id": str(other_sales_user.id)}
    )
    assert res.status_code == 403


def test_salesperson_cannot_see_other_routes(sales_client, other_sales_client, sales_user, wilson, fake_geo):
    plan = sales_client.post("/routes/optimize", json=plan_payload([wilson["derm"].id])).json()
    route = sales_client.post("/routes", json={"plan": plan}).json()

    assert other_sales_client.get(f"/routes/{route['id']}").status_code == 404
    assert other_sales_client.patch(f"/routes/{route['id']}", json={"status": "confirmed"}).status_code == 404
    assert other_sales_client.delete(f"/routes/{route['id']}").status_code == 404
    assert other_sales_client.post(f"/routes/{route['id']}/recalculate", json={}).status_code == 404
    assert other_sales_client.get("/routes").json() == []
    assert other_sales_client.get(f"/routes/by-date?salesperson_id={sales_user.id}&date={DAY}").status_code == 403


def test_admin_has_full_access(admin_client, sales_client, sales_user, wilson, fake_geo):
    plan = sales_client.post("/routes/optimize", json=plan_payload([wilson["derm"].id])).json()
    route = sales_client.post("/routes", json={"plan": plan}).json()
    assert admin_client.get(f"/routes/{route['id']}").status_code == 200
    assert len(admin_client.get(f"/routes?salesperson_id={sales_user.id}").json()) == 1
    # Admin can plan a salesperson's day, with any company
    res = admin_client.post(
        "/routes/optimize",
        json={**plan_payload([wilson["derm"].id, wilson["theirs"].id]), "salesperson_id": str(sales_user.id)},
    )
    assert res.status_code == 200, res.text
    # Admin can list all companies, not only assigned ones
    preview = admin_client.post(
        "/routes/preview",
        json={"start_location": GIG_EAST, "radius_miles": 20, "salesperson_id": str(sales_user.id), "scope": "all"},
    ).json()
    assert "Freedom Family Medicine" in {c["company_name"] for c in preview["candidates"]}


def test_priority_endpoint_permissions(sales_client, other_sales_client, admin_client, wilson):
    url = f"/prospects/{wilson['peds'].id}/priority"
    assert sales_client.patch(url, json={"priority": "high"}).status_code == 200
    assert other_sales_client.patch(url, json={"priority": "low"}).status_code == 403
    assert admin_client.patch(url, json={"priority": "low"}).status_code == 200
