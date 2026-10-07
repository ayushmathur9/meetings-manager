import json

import httpx
import pytest

from app.services.geoapify import (
    GeoapifyAuthError,
    GeoapifyBadRequestError,
    GeoapifyClient,
    GeoapifyNoRouteError,
    GeoapifyNotConfiguredError,
    GeoapifyRateLimitError,
    GeoapifyUnavailableError,
    InvalidCoordinatesError,
    PlannerJob,
    validate_coordinate,
)

KEY = "test-secret-key"
GIG_EAST = (35.7213, -77.9155)
CLINIC_A = (35.7305, -77.9515)
CLINIC_B = (35.7675, -77.9378)


class Recorder:
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make_client(handler) -> tuple[GeoapifyClient, Recorder]:
    recorder = Recorder(handler)
    return GeoapifyClient(api_key=KEY, transport=httpx.MockTransport(recorder), cache_ttl_seconds=60), recorder


# --------------------------------------------------------------------------- geocoding


def test_geocode_success_parses_and_rates_confidence():
    def handler(request):
        assert request.url.path == "/v1/geocode/search"
        assert request.url.params["apiKey"] == KEY
        assert request.url.params["filter"] == "countrycode:us"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "lat": 35.7213, "lon": -77.9155, "formatted": "127 Goldsboro St S, Wilson, NC 27893",
                        "housenumber": "127", "street": "Goldsboro Street South", "city": "Wilson",
                        "state": "North Carolina", "postcode": "27893", "country": "United States",
                        "place_id": "abc", "result_type": "building", "rank": {"confidence": 1},
                    },
                    {
                        "lat": 35.72, "lon": -77.91, "formatted": "Goldsboro St S, Wilson",
                        "place_id": "street", "result_type": "street", "rank": {"confidence": 0.7},
                    },
                    {"lat": 35.0, "lon": -77.0, "place_id": "weak", "result_type": "city", "rank": {"confidence": 0.2}},
                    {"lat": None, "lon": None, "place_id": "broken"},
                ]
            },
        )

    client, _ = make_client(handler)
    results = client.geocode_address("127 Goldsboro St S, Wilson, NC")
    assert [r.confidence for r in results] == ["high", "medium", "low"]
    top = results[0]
    assert (top.latitude, top.longitude) == (35.7213, -77.9155)
    assert top.address_line_1 == "127 Goldsboro Street South"
    assert top.city == "Wilson" and top.postal_code == "27893"


def test_geocode_is_cached():
    client, recorder = make_client(lambda r: httpx.Response(200, json={"results": []}))
    client.geocode_address("1 Main St, Wilson NC")
    client.geocode_address("1 Main St, Wilson NC")
    assert len(recorder.requests) == 1


def test_geocode_failure_auth_error_is_user_safe():
    client, _ = make_client(lambda r: httpx.Response(401, json={"statusCode": 401, "error": "Unauthorized", "message": "Invalid apiKey"}))
    with pytest.raises(GeoapifyAuthError) as exc:
        client.geocode_address("1 Main St, Wilson NC")
    assert KEY not in exc.value.user_message
    assert KEY not in str(exc.value)


def test_geocode_rejects_incomplete_address_without_calling_api():
    client, recorder = make_client(lambda r: httpx.Response(200, json={"results": []}))
    with pytest.raises(GeoapifyBadRequestError):
        client.geocode_address("  ")
    assert recorder.requests == []


def test_reverse_geocode():
    def handler(request):
        assert request.url.path == "/v1/geocode/reverse"
        assert request.url.params["lat"] == "35.7213"
        return httpx.Response(200, json={"results": [{"lat": 35.7213, "lon": -77.9155, "formatted": "Wilson", "result_type": "building", "rank": {"confidence": 0.95}}]})

    client, _ = make_client(handler)
    assert client.reverse_geocode(*GIG_EAST)[0].formatted_address == "Wilson"


def test_not_configured_raises_before_any_request():
    recorder = Recorder(lambda r: httpx.Response(200, json={}))
    client = GeoapifyClient(api_key="", transport=httpx.MockTransport(recorder))
    assert not client.is_configured
    with pytest.raises(GeoapifyNotConfiguredError):
        client.get_route([GIG_EAST, CLINIC_A])
    assert recorder.requests == []


# --------------------------------------------------------------------------- routing


def test_route_success():
    def handler(request):
        assert request.url.path == "/v1/routing"
        assert request.url.params["waypoints"] == "35.7213,-77.9155|35.7305,-77.9515"
        assert request.url.params["mode"] == "drive"
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "MultiLineString", "coordinates": [[[-77.9155, 35.7213], [-77.9515, 35.7305]]]},
                        "properties": {"distance": 4200, "time": 480.4, "legs": [{"distance": 4200, "time": 480.4}]},
                    }
                ],
            },
        )

    client, _ = make_client(handler)
    route = client.get_route([GIG_EAST, CLINIC_A])
    assert route.duration_seconds == 480
    assert route.distance_meters == 4200
    assert route.legs[0].duration_seconds == 480
    assert route.geometry == [[[-77.9155, 35.7213], [-77.9515, 35.7305]]]


def test_route_failure_no_features():
    client, _ = make_client(lambda r: httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
    with pytest.raises(GeoapifyNoRouteError):
        client.get_route([GIG_EAST, CLINIC_A])


def test_route_server_error_and_timeout():
    client, _ = make_client(lambda r: httpx.Response(503, text="down"))
    with pytest.raises(GeoapifyUnavailableError):
        client.get_route([GIG_EAST, CLINIC_A])

    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    client, _ = make_client(boom)
    with pytest.raises(GeoapifyUnavailableError):
        client.get_route([GIG_EAST, CLINIC_B])


def test_rate_limit():
    client, _ = make_client(lambda r: httpx.Response(429, json={"message": "Too many requests"}))
    with pytest.raises(GeoapifyRateLimitError):
        client.get_route([GIG_EAST, CLINIC_A])


# --------------------------------------------------------------------------- matrix


def test_matrix_dedupes_points_and_maps_results():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/routematrix"
        # GIG_EAST appears twice in the input but only once in the request.
        assert body["sources"] == [{"location": [-77.9155, 35.7213]}, {"location": [-77.9515, 35.7305]}]
        assert body["mode"] == "drive"
        return httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [
                        {"source_index": 0, "target_index": 0, "time": 0, "distance": 0},
                        {"source_index": 0, "target_index": 1, "time": 480, "distance": 4200},
                    ],
                    [
                        {"source_index": 1, "target_index": 0, "time": 500, "distance": 4300},
                        {"source_index": 1, "target_index": 1, "time": 0, "distance": 0},
                    ],
                ]
            },
        )

    client, recorder = make_client(handler)
    points = [GIG_EAST, CLINIC_A, GIG_EAST]
    matrix = client.get_route_matrix(points, points)
    assert matrix[0][1].duration_seconds == 480
    assert matrix[1][2].duration_seconds == 500  # CLINIC_A -> GIG_EAST (the end)
    assert matrix[0][2].duration_seconds == 0
    # Cached on second call
    client.get_route_matrix(points, points)
    assert len(recorder.requests) == 1


def test_matrix_unreachable_pairs_are_none():
    client, _ = make_client(
        lambda r: httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [{"source_index": 0, "target_index": 0, "time": 0, "distance": 0},
                     {"source_index": 0, "target_index": 1, "time": None, "distance": None}],
                    [{"source_index": 1, "target_index": 0, "time": None, "distance": None},
                     {"source_index": 1, "target_index": 1, "time": 0, "distance": 0}],
                ]
            },
        )
    )
    matrix = client.get_route_matrix([GIG_EAST, CLINIC_A], [GIG_EAST, CLINIC_A])
    assert matrix[0][1] is None and matrix[1][0] is None


def test_matrix_malformed_response():
    client, _ = make_client(lambda r: httpx.Response(200, json={"oops": True}))
    with pytest.raises(GeoapifyUnavailableError):
        client.get_route_matrix([GIG_EAST, CLINIC_A], [GIG_EAST, CLINIC_A])


# --------------------------------------------------------------------------- invalid coordinates


@pytest.mark.parametrize("point", [(None, None), (91, 0), (0, 181), (0, 0), (float("nan"), 1), ("x", 2)])
def test_invalid_coordinates_rejected(point):
    with pytest.raises(InvalidCoordinatesError):
        validate_coordinate(point)


def test_invalid_coordinates_never_reach_api():
    client, recorder = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(InvalidCoordinatesError):
        client.get_route_matrix([GIG_EAST, (0, 0)], [GIG_EAST])
    with pytest.raises(InvalidCoordinatesError):
        client.get_route([GIG_EAST, (95, 10)])
    assert recorder.requests == []


# --------------------------------------------------------------------------- route planner


def test_optimize_route_parses_order_and_unassigned():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/routeplanner"
        assert body["agents"][0]["start_location"] == [-77.9155, 35.7213]
        assert body["agents"][0]["end_location"] == [-77.9155, 35.7213]
        assert body["agents"][0]["time_windows"] == [[0, 28800]]
        assert body["jobs"][1]["priority"] == 100
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "properties": {"issues": {"unassigned_jobs": [2]}},
                "features": [
                    {"properties": {"actions": [
                        {"type": "start"},
                        {"type": "job", "job_index": 1},
                        {"type": "job", "job_index": 0},
                        {"type": "end"},
                    ]}}
                ],
            },
        )

    client, _ = make_client(handler)
    jobs = [
        PlannerJob("a", CLINIC_A, 1500, 50),
        PlannerJob("b", CLINIC_B, 1500, 100),
        PlannerJob("c", (35.9, -78.0), 1500, 10),
    ]
    result = client.optimize_route(GIG_EAST, jobs, end=GIG_EAST, available_seconds=28800)
    assert result.order == [1, 0]
    assert result.unassigned == [2]


def test_transient_failure_is_retried_once():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectTimeout("blip", request=request)
        return httpx.Response(200, json={"results": []})

    client, recorder = make_client(flaky)
    assert client.geocode_address("2563 Ward Blvd, Wilson, NC") == []
    assert len(recorder.requests) == 2


def test_persistent_server_error_gives_up_after_one_retry():
    client, recorder = make_client(lambda r: httpx.Response(502, text="bad gateway"))
    with pytest.raises(GeoapifyUnavailableError):
        client.get_route([GIG_EAST, CLINIC_A])
    assert len(recorder.requests) == 2


def test_client_errors_are_not_retried():
    client, recorder = make_client(lambda r: httpx.Response(401, json={"message": "Invalid apiKey"}))
    with pytest.raises(GeoapifyAuthError):
        client.get_route([GIG_EAST, CLINIC_A])
    assert len(recorder.requests) == 1
