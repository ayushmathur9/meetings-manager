"""Regression checks for existing features the route planner work touches."""

import io
from datetime import date, time

import pandas as pd

from app.models.meeting import Meeting
from app.models.route import Route, RouteStop
from app.tests.test_route_planner_api import GIG_EAST, add_company


def test_login_me_logout(app, admin_user):
    from fastapi.testclient import TestClient

    # Outside development the auth cookie is Secure (SameSite=None), so use https.
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/auth/login", json={"email": "admin@samtest.com", "password": "wrong"}).status_code == 401
    res = client.post("/auth/login", json={"email": "admin@samtest.com", "password": "Test@123"})
    assert res.status_code == 200
    assert "access_token" in res.cookies
    assert client.get("/auth/me").json()["email"] == "admin@samtest.com"
    client.post("/auth/logout")
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401


def test_company_crud(admin_client):
    created = admin_client.post(
        "/companies",
        json={"name": "Wilson Eye Associates", "industry": "Healthcare", "address_line_1": "2402 Montgomery Dr SW", "city": "Wilson", "state": "NC"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]
    assert admin_client.get(f"/companies/{company_id}").json()["name"] == "Wilson Eye Associates"
    patched = admin_client.patch(f"/companies/{company_id}", json={"phone": "252-555-0100"})
    assert patched.status_code == 200 and patched.json()["phone"] == "252-555-0100"
    listing = admin_client.get("/companies").json()
    assert any(c["id"] == company_id for c in listing["items"])
    assert admin_client.delete(f"/companies/{company_id}").status_code == 204
    assert admin_client.get(f"/companies/{company_id}").status_code == 404


def test_location_resolve_and_candidates(admin_client, db, sales_user):
    company = add_company(db, "Lee Dentistry", address="118 Brentwood Center Ln N")
    # No real provider configured in tests: honest empty candidate list, no fabrication.
    candidates = admin_client.get(f"/companies/{company.id}/location/candidates")
    assert candidates.status_code == 200 and candidates.json()["candidates"] == []
    resolved = admin_client.post(
        f"/companies/{company.id}/location/resolve",
        json={"candidate": {"formatted_address": "118 Brentwood Center Ln N, Wilson, NC", "latitude": 35.75, "longitude": -77.95,
                            "place_id": "x", "name": "Lee Dentistry", "confidence": "high", "city": "Wilson", "state": "NC"}},
    )
    assert resolved.status_code == 200, resolved.text
    location = resolved.json()["locations"][0]
    assert location["verification_status"] == "verified"
    assert location["latitude"] == 35.75


def test_verified_location_is_never_overwritten_by_automated_geocoding(db):
    from app.models.location import Location
    from app.providers.location.base import GeocodeResult, LocationCandidate, LocationProvider
    from app.services.location_service import LocationService

    company = add_company(db, "Signature Smiles", 35.7500, -77.9300)

    class EagerProvider(LocationProvider):
        name = "eager"

        def search_business(self, query, *, near=None):
            return GeocodeResult([LocationCandidate("Elsewhere", 36.0, -78.0, "p", confidence="high")], query, self.name)

        geocode_address = lambda self, a: self.search_business(a)  # noqa: E731
        reverse_geocode = calculate_distance = calculate_travel_time = calculate_travel_time_matrix = None
        create_navigation_link = None

    location, _, _ = LocationService(db, EagerProvider()).verify_company_location(
        company_id=company.id, company_name=company.name, raw_address="2250 Nash St N", city="Wilson", state="NC"
    )
    stored = db.query(Location).filter(Location.company_id == company.id).one()
    assert (stored.latitude, stored.longitude) == (35.75, -77.93)
    assert location.id == stored.id


def test_excel_import_flow(admin_client):
    frame = pd.DataFrame(
        [
            {"Company Name": "Joyner Chiropractic", "Address": "2258 Nash St N", "City": "Wilson", "State": "NC", "Phone": "252-555-0101"},
            {"Company Name": "Wilson Family Dental", "Address": "2563 Ward Blvd", "City": "Wilson", "State": "NC", "Phone": "252-555-0102"},
        ]
    )
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    upload = admin_client.post(
        "/imports",
        files={"file": ("prospects.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 201, upload.text
    preview = upload.json()
    assert preview["row_count"] == 2
    mapping = {field: column for field, column in preview["suggested_mapping"].items() if column}
    assert mapping.get("company_name") == "Company Name"
    validated = admin_client.post(f"/imports/{preview['import_id']}/mapping", json={"mapping": mapping})
    assert validated.status_code == 200, validated.text
    confirmed = admin_client.post(f"/imports/{preview['import_id']}/confirm", json={"verify_locations": True})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["import_job"]["status"] in ("completed", "completed_with_errors")
    names = {c["name"] for c in admin_client.get("/companies").json()["items"]}
    assert {"Joyner Chiropractic", "Wilson Family Dental"} <= names


def test_prospect_list_for_map_still_works(admin_client, sales_client, db, sales_user):
    add_company(db, "Wilson Medical Group", 35.7675, -77.9378, assigned_to=sales_user)
    add_company(db, "Unassigned Clinic", 35.76, -77.93)
    admin_items = admin_client.get(
        f"/prospects?center_lat={GIG_EAST['latitude']}&center_lng={GIG_EAST['longitude']}&radius_miles=20"
    ).json()["items"]
    assert {i["company_name"] for i in admin_items} == {"Wilson Medical Group", "Unassigned Clinic"}
    assert all(i["latitude"] and i["distance_meters"] is not None for i in admin_items)
    assert admin_items[0]["priority"] == "medium"
    sales_items = sales_client.get("/prospects").json()["items"]
    assert [i["company_name"] for i in sales_items] == ["Wilson Medical Group"]


def test_legacy_by_date_route_and_navigation(db, sales_client, sales_user):
    company = add_company(db, "Eastern Carolina Pediatrics", 35.7234, -77.9430, assigned_to=sales_user)
    meeting = Meeting(
        company_id=company.id, salesperson_id=sales_user.id, date=date(2026, 10, 12), start_time=time(9, 0),
        end_time=time(9, 25), duration_minutes=25, created_by_id=sales_user.id,
        location_id=company.locations[0].id if company.locations else None,
    )
    db.add(meeting)
    db.flush()
    route = Route(salesperson_id=sales_user.id, date=date(2026, 10, 12), start_location=GIG_EAST)
    route.stops = [RouteStop(meeting_id=meeting.id, sequence=1, arrival_time=time(9, 0), departure_time=time(9, 25))]
    db.add(route)
    db.commit()

    res = sales_client.get(f"/routes/by-date?salesperson_id={sales_user.id}&date=2026-10-12")
    assert res.status_code == 200
    assert res.json()["stops"][0]["company_name"] == "Eastern Carolina Pediatrics"
    # Legacy routes also open in the new planner format
    reopened = sales_client.get(f"/routes/{route.id}")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["stops"][0]["company_name"] == "Eastern Carolina Pediatrics"

    nav = sales_client.get("/navigation/link?dest_lat=35.7234&dest_lng=-77.943").json()["url"]
    assert nav.startswith("https://www.google.com/maps/dir/?") and "35.7234" in nav
