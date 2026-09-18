"""Geocode/verify companies that don't have a confirmed location yet.

Run after fixing the configured map provider credentials (MAPBOX_ACCESS_TOKEN
or GOOGLE_MAPS_API_KEY) to retroactively verify companies that were imported
while the credential was invalid/missing — they were correctly left as
"needs verification" rather than given a fabricated location at import time.

Run with: poetry run python -m app.geocode_pending
"""

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.location import Location, VerificationStatus
from app.providers.location import get_location_provider
from app.services.location_service import LocationService
from app.services.normalization import parse_combined_address


def geocode_pending() -> None:
    provider = get_location_provider()
    print(f"Using location provider: {provider.name}")
    if provider.name == "fallback_estimate":
        print(
            "No real geocoding credential is configured (still using the "
            "distance-estimate-only fallback) — nothing to do. Set a valid "
            "MAPBOX_ACCESS_TOKEN or GOOGLE_MAPS_API_KEY first."
        )
        return

    db = SessionLocal()
    try:
        location_service = LocationService(db, provider)

        pending = (
            db.query(Company, Location)
            .join(Location, Location.company_id == Company.id)
            .filter(Location.verification_status != VerificationStatus.VERIFIED)
            .all()
        )
        print(f"{len(pending)} compan(ies) pending verification")

        verified = 0
        still_pending = 0
        for company, location in pending:
            raw_address = location.address_line_1
            city = location.city
            state = location.state
            postal_code = location.postal_code

            # Same combined-address fallback as import: older Location rows
            # (imported before this parsing existed) may have "Street, City,
            # State ZIP" all crammed into address_line_1 with no city/state
            # of their own — split it out so the sanity check has something
            # to compare against.
            if raw_address and not (city and state):
                parsed = parse_combined_address(raw_address)
                if parsed["city"] and parsed["state"]:
                    raw_address = parsed["street"]
                    city = city or parsed["city"]
                    state = state or parsed["state"]
                    postal_code = postal_code or parsed["postal_code"]

            try:
                result, candidates, reason = location_service.verify_company_location(
                    company_id=company.id,
                    company_name=company.name,
                    raw_address=raw_address,
                    city=city,
                    state=state,
                    postal_code=postal_code,
                    country=location.country,
                )
            except Exception as exc:
                message = str(exc).split("access_token=")[0].rstrip("&?")
                location_service.mark_failed(
                    company_id=company.id,
                    raw_address=raw_address,
                    notes=f"Location lookup failed: {message}",
                    city=city,
                    state=state,
                    postal_code=postal_code,
                )
                print(f"  ERROR  {company.name}: {message}")
                still_pending += 1
                continue

            if result is not None:
                verified += 1
                print(f"  OK     {company.name} -> {result.latitude:.5f},{result.longitude:.5f}")
            else:
                still_pending += 1
                if not reason:
                    reason = f"{len(candidates)} ambiguous candidate(s)" if candidates else "no match found"
                location_service.mark_needs_verification(
                    company_id=company.id,
                    raw_address=raw_address,
                    notes=reason,
                    city=city,
                    state=state,
                    postal_code=postal_code,
                )
                print(f"  REVIEW {company.name}: {reason}")

        db.commit()
        print(f"\nVerified {verified}, still needing review {still_pending}")
    finally:
        db.close()


if __name__ == "__main__":
    geocode_pending()
