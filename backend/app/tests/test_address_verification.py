"""Automatic address verification: on create, on address edit, and in the
background sweep — plus the Geoapify match-quality rules behind it."""

from datetime import datetime, timedelta, timezone

import httpx

from app.models.company import Company
from app.models.location import Location, VerificationStatus
from app.providers.location.base import GeocodeResult, LocationCandidate, LocationProvider
from app.providers.location.fallback import FallbackLocationProvider
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.company_service import CompanyService
from app.services.geoapify import GeoapifyClient, GeoapifyUnavailableError, _classify_confidence, split_house_number
from app.services.location_service import LocationService
from app.services.location_sweep import pending_locations_query, run_location_sweep

WILSON_EYE = LocationCandidate(
    "2402 Montgomery Dr SW, Wilson, NC 27893", 35.7069, -77.9456, "wilson-eye",
    address_line_1="2402 Montgomery Dr SW", city="Wilson", state="NC", postal_code="27893", confidence="high",
)
NASH_ST = LocationCandidate(
    "2250 Nash St N, Wilson, NC 27896", 35.7500, -77.9300, "nash-st",
    address_line_1="2250 Nash St N", city="Wilson", state="NC", postal_code="27896", confidence="high",
)


class FakeProvider(LocationProvider):
    """Name searches find nothing; structured lookups return ``by_street``."""

    name = "fake"

    def __init__(self, by_street=None, error=None):
        self.by_street = by_street or {}
        self.error = error
        self.structured_calls = []

    def search_business(self, query, *, near=None):
        if self.error:
            raise self.error
        return GeocodeResult([], query, self.name)

    def geocode_address(self, address):
        return GeocodeResult([], address, self.name)

    def geocode_structured(self, *, street, city=None, state=None, postal_code=None, country=None):
        self.structured_calls.append((street, city, state, postal_code))
        hit = self.by_street.get(street)
        return GeocodeResult([hit] if hit else [], street, self.name)

    reverse_geocode = calculate_distance = calculate_travel_time = calculate_travel_time_matrix = None
    create_navigation_link = None


def _primary(db, company_id) -> Location:
    return db.query(Location).filter(Location.company_id == company_id, Location.is_primary.is_(True)).one()


# --------------------------------------------------------------------------- Geoapify match quality


def test_split_house_number():
    assert split_house_number("2402 Montgomery Dr SW") == ("2402", "Montgomery Dr SW")
    assert split_house_number("12B Main St") == ("12B", "Main St")
    assert split_house_number("One Market Plaza") == (None, "One Market Plaza")
    assert split_house_number(None) == (None, None)


def test_street_level_match_is_never_high_confidence():
    # Geoapify placed the point on the street, not at the house number.
    result = {"result_type": "building", "rank": {"confidence": 0.95, "match_type": "match_by_street"}}
    assert _classify_confidence(result) == "medium"


def test_building_level_confidence_beats_name_noise():
    # "<company> <address>" drags the overall score down for the unmatched
    # name words even though the building matched exactly.
    result = {
        "result_type": "building",
        "rank": {"confidence": 0.5, "confidence_building_level": 1, "match_type": "full_match"},
    }
    assert _classify_confidence(result) == "high"


def test_structured_geocode_sends_each_part_separately():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"results": []})

    client = GeoapifyClient(api_key="k", transport=httpx.MockTransport(handler), cache_ttl_seconds=60)
    client.geocode_structured(street="2402 Montgomery Dr SW", city="Wilson", state="NC", postal_code="27893")
    params = seen[0]
    assert params["housenumber"] == "2402"
    assert params["street"] == "Montgomery Dr SW"
    assert (params["city"], params["state"], params["postcode"]) == ("Wilson", "NC", "27893")
    assert "text" not in params


# --------------------------------------------------------------------------- create / edit


def test_new_company_address_is_verified_on_create(db):
    provider = FakeProvider({"2402 Montgomery Dr SW": WILSON_EYE})
    company = CompanyService(db, provider).create_company(
        CompanyCreate(name="Wilson Eye Associates", address_line_1="2402 Montgomery Dr SW", city="Wilson", state="NC")
    )
    location = _primary(db, company.id)
    assert location.verification_status == VerificationStatus.VERIFIED
    assert (location.latitude, location.longitude) == (35.7069, -77.9456)
    assert location.postal_code == "27893"  # filled in from the geocoder
    assert location.geocode_attempts == 1


def test_create_without_geocoder_stays_unverified_for_the_sweep(db):
    company = CompanyService(db, FallbackLocationProvider()).create_company(
        CompanyCreate(name="Nash Clinic", address_line_1="2250 Nash St N", city="Wilson", state="NC")
    )
    location = _primary(db, company.id)
    assert location.verification_status == VerificationStatus.UNVERIFIED
    assert location.geocode_attempts == 0


def test_combined_address_is_split_before_lookup(db):
    provider = FakeProvider({"2402 Montgomery Dr SW": WILSON_EYE})
    company = CompanyService(db, provider).create_company(
        CompanyCreate(name="Wilson Eye Associates", address_line_1="2402 Montgomery Dr SW, Wilson, NC 27893")
    )
    assert provider.structured_calls[0] == ("2402 Montgomery Dr SW", "Wilson", "NC", "27893")
    assert _primary(db, company.id).verification_status == VerificationStatus.VERIFIED


def test_editing_the_address_replaces_a_verified_location(db):
    provider = FakeProvider({"2402 Montgomery Dr SW": WILSON_EYE, "2250 Nash St N": NASH_ST})
    service = CompanyService(db, provider)
    company = service.create_company(
        CompanyCreate(name="Wilson Eye Associates", address_line_1="2402 Montgomery Dr SW", city="Wilson", state="NC")
    )
    db.refresh(company)

    service.update_company(company, CompanyUpdate(address_line_1="2250 Nash St N"))
    location = _primary(db, company.id)
    assert location.verification_status == VerificationStatus.VERIFIED
    assert (location.latitude, location.longitude) == (35.75, -77.93)
    assert db.query(Location).filter(Location.company_id == company.id).count() == 1


def test_unchanged_address_in_patch_does_not_relookup(db):
    provider = FakeProvider({"2402 Montgomery Dr SW": WILSON_EYE})
    service = CompanyService(db, provider)
    company = service.create_company(
        CompanyCreate(name="Wilson Eye Associates", address_line_1="2402 Montgomery Dr SW", city="Wilson", state="NC")
    )
    db.refresh(company)
    calls = len(provider.structured_calls)
    service.update_company(company, CompanyUpdate(city="Wilson", phone="252-555-0100"))
    assert len(provider.structured_calls) == calls


def test_unmatched_edit_is_flagged_for_review_not_left_with_old_coordinates(db):
    provider = FakeProvider({"2402 Montgomery Dr SW": WILSON_EYE})
    service = CompanyService(db, provider)
    company = service.create_company(
        CompanyCreate(name="Wilson Eye Associates", address_line_1="2402 Montgomery Dr SW", city="Wilson", state="NC")
    )
    db.refresh(company)
    service.update_company(company, CompanyUpdate(address_line_1="999 Nowhere Rd"))
    location = _primary(db, company.id)
    assert location.verification_status == VerificationStatus.NEEDS_REVIEW
    assert location.latitude is None
    assert location.address_line_1 == "999 Nowhere Rd"


def test_provider_error_is_recorded_as_failed(db):
    provider = FakeProvider(error=GeoapifyUnavailableError("timed out"))
    company = CompanyService(db, provider).create_company(
        CompanyCreate(name="Nash Clinic", address_line_1="2250 Nash St N", city="Wilson", state="NC")
    )
    location = _primary(db, company.id)
    assert location.verification_status == VerificationStatus.FAILED
    assert "timed out" in location.verification_notes


def test_address_edit_via_api(admin_client):
    created = admin_client.post("/companies", json={"name": "Lee Dentistry", "city": "Wilson", "state": "NC"})
    company_id = created.json()["id"]
    patched = admin_client.patch(f"/companies/{company_id}", json={"address_line_1": "118 Brentwood Center Ln N"})
    assert patched.status_code == 200, patched.text
    location = patched.json()["locations"][0]
    assert location["address_line_1"] == "118 Brentwood Center Ln N"
    assert location["city"] == "Wilson"


# --------------------------------------------------------------------------- background sweep


def _unverified_company(db, name, street, *, attempts=0, last_attempt=None) -> Company:
    company = Company(name=name, normalized_name=name.lower())
    db.add(company)
    db.flush()
    db.add(Location(
        company_id=company.id, is_primary=True, address_line_1=street, city="Wilson", state="NC",
        geocode_attempts=attempts, last_geocode_attempt_at=last_attempt,
    ))
    db.flush()
    return company


def test_sweep_verifies_pending_companies(db):
    company = _unverified_company(db, "Nash Clinic", "2250 Nash St N")
    stats = run_location_sweep(db, FakeProvider({"2250 Nash St N": NASH_ST}))
    assert stats.verified == 1
    assert _primary(db, company.id).verification_status == VerificationStatus.VERIFIED


def test_sweep_backs_off_and_eventually_gives_up(db):
    now = datetime.now(timezone.utc)
    fresh = _unverified_company(db, "Never Tried", "1 A St")
    recent = _unverified_company(db, "Tried Recently", "2 B St", attempts=1, last_attempt=now - timedelta(hours=1))
    due = _unverified_company(db, "Due Again", "3 C St", attempts=1, last_attempt=now - timedelta(hours=13))
    exhausted = _unverified_company(db, "Gave Up", "4 D St", attempts=5, last_attempt=now - timedelta(days=60))

    due_ids = {company.id for company, _ in pending_locations_query(db).all()}
    assert fresh.id in due_ids and due.id in due_ids
    assert recent.id not in due_ids and exhausted.id not in due_ids

    # A forced run (python -m app.geocode_pending) ignores the backoff.
    all_ids = {company.id for company, _ in pending_locations_query(db, respect_backoff=False).all()}
    assert {recent.id, exhausted.id} <= all_ids


def test_sweep_does_nothing_without_a_geocoder(db):
    company = _unverified_company(db, "Nash Clinic", "2250 Nash St N")
    assert run_location_sweep(db, FallbackLocationProvider()).checked == 0
    assert _primary(db, company.id).geocode_attempts == 0


def test_verify_or_flag_counts_attempts(db):
    company = _unverified_company(db, "Nowhere Co", "999 Nowhere Rd")
    service = LocationService(db, FakeProvider())
    for _ in range(2):
        service.verify_or_flag(company_id=company.id, company_name=company.name, raw_address="999 Nowhere Rd",
                               city="Wilson", state="NC")
    location = _primary(db, company.id)
    assert location.geocode_attempts == 2
    assert location.verification_status == VerificationStatus.NEEDS_REVIEW
