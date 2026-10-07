"""Geocode/verify companies that don't have a confirmed location yet.

The API server already does this automatically in the background (see
services/location_sweep.py), with a retry backoff. Run this to force an
immediate pass over *every* unverified company regardless of backoff — e.g.
right after fixing the geocoding credential (GEOAPIFY_API_KEY, or
MAPBOX_ACCESS_TOKEN / GOOGLE_MAPS_API_KEY for those providers).

Run with: poetry run python -m app.geocode_pending

Already-verified locations are never touched.
"""

from app.db.session import SessionLocal
from app.models.location import VerificationStatus
from app.providers.location import get_geocoding_provider
from app.providers.location.fallback import FallbackLocationProvider
from app.services.location_sweep import pending_locations_query, run_location_sweep


def geocode_pending() -> None:
    provider = get_geocoding_provider()
    print(f"Using location provider: {provider.name}")
    if provider.name == FallbackLocationProvider.name:
        print(
            "No real geocoding credential is configured (still using the "
            "distance-estimate-only fallback) — nothing to do. Set a valid "
            "GEOAPIFY_API_KEY (or MAPBOX_ACCESS_TOKEN / GOOGLE_MAPS_API_KEY) first."
        )
        return

    db = SessionLocal()
    try:
        print(f"{pending_locations_query(db, respect_backoff=False).count()} compan(ies) pending verification")

        def report(company, location) -> None:
            if location.verification_status == VerificationStatus.VERIFIED:
                print(f"  OK     {company.name} -> {location.latitude:.5f},{location.longitude:.5f}")
            elif location.verification_status == VerificationStatus.FAILED:
                print(f"  ERROR  {company.name}: {location.verification_notes}")
            else:
                print(f"  REVIEW {company.name}: {location.verification_notes}")

        stats = run_location_sweep(db, provider, respect_backoff=False, on_result=report)
        print(f"\nVerified {stats.verified}, still needing review {stats.needs_review + stats.failed}")
    finally:
        db.close()


if __name__ == "__main__":
    geocode_pending()
