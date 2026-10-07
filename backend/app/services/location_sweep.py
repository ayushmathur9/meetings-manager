"""Background verification of company addresses that aren't verified yet.

Addresses can end up unverified for reasons that fix themselves later: the
geocoding key wasn't configured when the company was saved, Geoapify timed
out, or a lookup improvement has shipped since. The sweep retries those rows
on a schedule so nobody has to remember to run ``app.geocode_pending``.

Retries back off exponentially per row (``location_retry_base_hours`` x
2^attempts) and stop after ``location_retry_max_attempts`` — an address no
geocoder can resolve needs a person (the "Review location" screen), not
another identical API call. Editing the address resets the counter.

Only one process sweeps at a time (Postgres advisory lock), so running
several API replicas never doubles the Geoapify usage.
"""

import logging
import threading
from dataclasses import dataclass

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.company import Company
from app.models.location import Location, VerificationStatus
from app.providers.location import get_geocoding_provider
from app.providers.location.base import LocationProvider
from app.providers.location.fallback import FallbackLocationProvider
from app.services.location_service import LocationService

logger = logging.getLogger("app.location_sweep")

# Arbitrary constant identifying this job's pg advisory lock.
_ADVISORY_LOCK_KEY = 0x10CA7E5


@dataclass
class SweepStats:
    checked: int = 0
    verified: int = 0
    needs_review: int = 0
    failed: int = 0


def pending_locations_query(db: Session, *, respect_backoff: bool = True):
    """Primary locations that have an address but aren't verified, oldest
    attempt first. With ``respect_backoff`` only rows due for a retry."""
    settings = get_settings()
    query = (
        db.query(Company, Location)
        .join(Location, Location.company_id == Company.id)
        .filter(
            Location.is_primary.is_(True),
            Location.verification_status != VerificationStatus.VERIFIED,
            or_(
                Location.address_line_1.isnot(None),
                Location.city.isnot(None),
                Location.state.isnot(None),
                Location.postal_code.isnot(None),
            ),
        )
    )
    if respect_backoff:
        retry_after = func.make_interval(
            0, 0, 0, 0,
            cast(settings.location_retry_base_hours * func.power(2, Location.geocode_attempts), Integer),
        )
        query = query.filter(
            Location.geocode_attempts < settings.location_retry_max_attempts,
            or_(
                Location.last_geocode_attempt_at.is_(None),
                Location.last_geocode_attempt_at + retry_after <= func.now(),
            ),
        )
    return query.order_by(Location.last_geocode_attempt_at.asc().nulls_first())


def run_location_sweep(
    db: Session,
    provider: LocationProvider,
    *,
    limit: int | None = None,
    respect_backoff: bool = True,
    on_result=None,
) -> SweepStats:
    """Verify pending locations, committing after each company so progress
    survives an interruption. ``on_result(company, location)`` is called per
    row (used by the CLI for progress output)."""
    stats = SweepStats()
    if provider.name == FallbackLocationProvider.name:
        return stats

    service = LocationService(db, provider)
    query = pending_locations_query(db, respect_backoff=respect_backoff)
    if limit:
        query = query.limit(limit)

    for company, location in query.all():
        result = service.verify_or_flag(
            company_id=company.id,
            company_name=company.name,
            raw_address=location.address_line_1,
            city=location.city,
            state=location.state,
            postal_code=location.postal_code,
            country=location.country,
        )
        db.commit()
        stats.checked += 1
        status = result.verification_status if result is not None else None
        if status == VerificationStatus.VERIFIED:
            stats.verified += 1
        elif status == VerificationStatus.FAILED:
            stats.failed += 1
        else:
            stats.needs_review += 1
        if on_result is not None:
            on_result(company, result)
    return stats


def sweep_once() -> SweepStats | None:
    """One scheduled run: skip if no geocoder is configured or another
    process already holds the sweep lock."""
    from app.db.session import SessionLocal, engine

    provider = get_geocoding_provider()
    if provider.name == FallbackLocationProvider.name:
        return None

    settings = get_settings()
    with engine.connect() as lock_conn:
        if not lock_conn.execute(select(func.pg_try_advisory_lock(_ADVISORY_LOCK_KEY))).scalar():
            return None
        try:
            db = SessionLocal()
            try:
                stats = run_location_sweep(db, provider, limit=settings.location_sweep_batch_size)
            finally:
                db.close()
        finally:
            lock_conn.execute(select(func.pg_advisory_unlock(_ADVISORY_LOCK_KEY)))
            lock_conn.commit()

    if stats.checked:
        logger.info(
            "Location sweep: checked %d, verified %d, needs review %d, failed %d",
            stats.checked, stats.verified, stats.needs_review, stats.failed,
        )
    return stats


_STARTUP_DELAY_SECONDS = 60


def start_location_sweeper() -> threading.Event | None:
    """Start the periodic sweep in a daemon thread. Returns an Event that
    stops it when set, or None when disabled (interval 0, or tests)."""
    settings = get_settings()
    interval_minutes = settings.location_sweep_interval_minutes
    if interval_minutes <= 0 or settings.environment == "test":
        return None

    stop = threading.Event()

    def loop() -> None:
        if stop.wait(_STARTUP_DELAY_SECONDS):
            return
        while True:
            try:
                sweep_once()
            except Exception:
                logger.exception("Location sweep failed")
            if stop.wait(interval_minutes * 60):
                return

    threading.Thread(target=loop, name="location-sweep", daemon=True).start()
    return stop
