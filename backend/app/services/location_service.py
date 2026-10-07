"""Wraps a LocationProvider to verify and persist Company locations.

This is the only place that decides how a raw provider result becomes a
Location row. It always records source/provider/query/place_id/confidence/
timestamp (spec rule: never lose provenance) and never silently guesses when
a search is ambiguous — ambiguous results come back as multiple candidates
for a human to choose from, they are never auto-applied.

Lookup sequence (strongest signal first, falling back only when the previous
step found nothing or was ambiguous):
  1. Company name + full street address (+ city/state/zip context)
  2. Structured address geocoding — street, city, state and ZIP each sent
     in their own field (only when a street plus city/state or ZIP exist),
     which matches the exact building far more reliably than free text
  3. Company name + city/state/zip (no street address available)
  4. Plain address geocoding of whatever address text is available (no
     business-name matching — used as a last resort when business search
     can't find the place by name)

Every accepted candidate is checked against the *imported* city/state before
being trusted: a geocoder confidently returning the wrong city (e.g. a
company imported as "Wilson, NC" resolving to "Austin, TX") is a real and
observed failure mode, not a hypothetical, so it is never silently accepted.
A mismatch downgrades the result to NEEDS_REVIEW with an explanatory note
instead of being marked VERIFIED.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.models.location import Location, LocationSource, VerificationStatus
from app.providers.location.base import GeocodeResult, LocationCandidate, LocationProvider
from app.providers.location.fallback import FallbackLocationProvider
from app.services.normalization import (
    build_address_string,
    normalize_city,
    normalize_state,
    parse_combined_address,
)

_CONFIDENT = ("high", "medium")

# Lookup kinds, strongest signal first (see module docstring).
_BUSINESS = "business"
_STRUCTURED = "structured"
_ADDRESS = "address"


@dataclass(frozen=True)
class _Lookup:
    query: str  # human-readable; persisted as Location.search_query
    kind: str
    parts: tuple[str | None, str | None, str | None, str | None] | None = None  # street, city, state, zip


class LocationService:
    def __init__(self, db: Session, provider: LocationProvider) -> None:
        self.db = db
        self.provider = provider

    def search_candidates(
        self,
        *,
        company_name: str,
        raw_address: str | None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country: str | None = None,
    ) -> list[LocationCandidate]:
        """Read-only lookup: run the same fallback query chain as
        verify_company_location but never persist anything. Used to let a
        human browse candidates (e.g. a "review this location" screen)
        without a GET request silently writing to the database.
        """
        all_candidates: list[LocationCandidate] = []
        seen_places: set[str] = set()
        for lookup in self._lookup_queries(
            company_name=company_name,
            raw_address=raw_address,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
        ):
            for candidate in self._run_lookup(lookup).candidates:
                # Several lookups often find the same place — show it once.
                if candidate.place_id and candidate.place_id in seen_places:
                    continue
                if candidate.place_id:
                    seen_places.add(candidate.place_id)
                all_candidates.append(candidate)
        return all_candidates

    def verify_company_location(
        self,
        *,
        company_id,
        company_name: str,
        raw_address: str | None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country: str | None = None,
    ) -> tuple[Location | None, list[LocationCandidate], str | None]:
        """Attempt to verify a company's real-world location.

        Returns (location, candidates, reason):
          - If exactly one high/medium-confidence match is found AND its
            city/state matches the imported city/state (when both are
            known), a Location row is created/updated and returned as
            `location`; `candidates` and `reason` are empty/None.
          - Otherwise `location` is None, `candidates` holds what was found
            for human review, and `reason` explains why nothing was accepted
            (e.g. a geographic mismatch) so the caller can persist an
            informative "needs review" note — nothing is fabricated, silently
            picked, or accepted despite disagreeing with the imported city/state.
        """
        # Never replace an already-verified location (manually resolved or
        # previously geocoded with confidence) with a fresh automated lookup —
        # changing a verified location is a deliberate human action
        # (apply_candidate), not something a background geocode should do.
        existing = (
            self.db.query(Location)
            .filter(Location.company_id == company_id, Location.is_primary.is_(True))
            .first()
        )
        if (
            existing is not None
            and existing.verification_status == VerificationStatus.VERIFIED
            and existing.latitude is not None
            and existing.longitude is not None
        ):
            return existing, [], None

        expected_city = normalize_city(city)
        expected_state = normalize_state(state)
        all_candidates: list[LocationCandidate] = []

        for lookup in self._lookup_queries(
            company_name=company_name,
            raw_address=raw_address,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
        ):
            result = self._run_lookup(lookup)
            all_candidates.extend(result.candidates)

            # Accept only when exactly one candidate reaches "high" confidence
            # (a strong address-text match, not just "the provider only
            # suggested one thing") — multiple high-confidence candidates is a
            # genuine ambiguity, not a result to auto-pick from.
            high_confidence = [c for c in result.candidates if c.confidence == "high"]
            if len(high_confidence) != 1:
                continue

            candidate = high_confidence[0]
            if self._geographic_mismatch(candidate, expected_city, expected_state):
                # A confident single match that's in the wrong place entirely —
                # keep looking with the remaining (weaker) queries rather than
                # accepting it, but remember it as a candidate for review.
                continue

            source = LocationSource.VERIFIED_BUSINESS if lookup.kind == _BUSINESS else LocationSource.GEOCODED
            location = self._persist_verified_location(
                company_id=company_id, candidate=candidate, search_query=lookup.query, source=source
            )
            return location, [], None

        # Nothing was accepted. If every confident match we saw was rejected
        # specifically for a geographic mismatch (not just "too many
        # candidates"), surface that reason so a human sees why.
        confident = [c for c in all_candidates if c.confidence in _CONFIDENT]
        mismatched = [c for c in confident if self._geographic_mismatch(c, expected_city, expected_state)]
        reason = None
        if confident and len(mismatched) == len(confident):
            reason = (
                f"Geocoder returned {mismatched[0].city}, {mismatched[0].state}, which doesn't match "
                f"the imported location ({city or '?'}, {state or '?'})."
            )

        return None, all_candidates, reason

    def _lookup_queries(
        self,
        *,
        company_name: str,
        raw_address: str | None,
        city: str | None,
        state: str | None,
        postal_code: str | None,
        country: str | None,
    ):
        """Yield _Lookup steps in strongest-signal-first order."""
        full_address = build_address_string(
            address_line_1=raw_address, city=city, state=state, postal_code=postal_code, country=country
        )
        locality_only = build_address_string(city=city, state=state, postal_code=postal_code, country=country)

        seen: set[tuple[str, str]] = set()

        def emit(query: str | None, kind: str, parts=None):
            if query and (kind, query) not in seen:
                seen.add((kind, query))
                yield _Lookup(query=query, kind=kind, parts=parts)

        if full_address:
            yield from emit(f"{company_name} {full_address}", _BUSINESS)
        if raw_address and (postal_code or (city and state)):
            yield from emit(full_address, _STRUCTURED, (raw_address, city, state, postal_code))
        if locality_only:
            yield from emit(f"{company_name} {locality_only}", _BUSINESS)
        if raw_address:
            yield from emit(full_address or raw_address, _ADDRESS)

    def _run_lookup(self, lookup: _Lookup) -> GeocodeResult:
        if lookup.kind == _BUSINESS:
            return self.provider.search_business(lookup.query)
        if lookup.kind == _STRUCTURED:
            street, city, state, postal_code = lookup.parts
            return self.provider.geocode_structured(
                street=street, city=city, state=state, postal_code=postal_code
            )
        return self.provider.geocode_address(lookup.query)

    def _geographic_mismatch(
        self, candidate: LocationCandidate, expected_city: str | None, expected_state: str | None
    ) -> bool:
        """True when we have an expected city/state and the candidate clearly
        disagrees. Missing expectations (nothing to compare against) or a
        candidate missing its own city/state are never treated as a mismatch
        — only a concrete disagreement counts."""
        if expected_state:
            candidate_state = normalize_state(candidate.state)
            if candidate_state and candidate_state != expected_state:
                return True
        if expected_city:
            candidate_city = normalize_city(candidate.city)
            if candidate_city and candidate_city != expected_city:
                return True
        return False

    def verify_or_flag(
        self,
        *,
        company_id,
        company_name: str,
        raw_address: str | None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country: str | None = None,
    ) -> Location | None:
        """Run verify_company_location and record the outcome either way.

        The one entry point for automated verification (import, company
        create/edit, the background sweep, geocode_pending): a confident match
        is saved as VERIFIED, anything else is flagged NEEDS_REVIEW with a
        reason, and a provider error is recorded as FAILED — it never raises
        for a lookup problem, so callers can't half-save a company.

        Does nothing (returns the current primary location, if any) when no
        address is known or no real geocoder is configured — leaving the row
        UNVERIFIED so the background sweep picks it up once one is.
        """
        if not (raw_address or city or state or postal_code):
            return self._get_primary(company_id)
        if self.provider.name == FallbackLocationProvider.name:
            return self._get_primary(company_id)

        # A single "Street, City, State ZIP" string with no separate
        # city/state is common in spreadsheets and in older rows — split it
        # so the structured lookup and the wrong-city sanity check have
        # something to work with.
        if raw_address and not (city and state):
            parsed = parse_combined_address(raw_address)
            if parsed["city"] and parsed["state"]:
                raw_address = parsed["street"]
                city = city or parsed["city"]
                state = state or parsed["state"]
                postal_code = postal_code or parsed["postal_code"]

        existing = self._get_primary(company_id)
        if existing is not None and existing.verification_status == VerificationStatus.VERIFIED:
            return existing

        fields = dict(raw_address=raw_address, city=city, state=state, postal_code=postal_code, country=country)
        try:
            location, candidates, reason = self.verify_company_location(
                company_id=company_id, company_name=company_name, **fields
            )
        except Exception as exc:
            # Provider errors can embed the request URL (and so a credential) — trim it.
            message = str(exc).split("access_token=")[0].split("apiKey=")[0].rstrip("&?")
            location = self.mark_failed(
                company_id=company_id, notes=f"Location lookup failed: {message}"[:1000], **fields
            )
        else:
            if location is None:
                if not reason:
                    reason = (
                        f"{len(candidates)} possible match(es) found — none confident enough"
                        if candidates
                        else "No matching location found"
                    )
                location = self.mark_needs_verification(company_id=company_id, notes=reason, **fields)

        location.geocode_attempts = (location.geocode_attempts or 0) + 1
        location.last_geocode_attempt_at = datetime.now(timezone.utc)
        self.db.flush()
        return location

    def replace_address(
        self,
        *,
        company_id,
        company_name: str,
        address_line_1: str | None,
        city: str | None,
        state: str | None,
        postal_code: str | None,
        country: str | None,
        verify: bool = True,
    ) -> Location:
        """The company's address changed (a person corrected it, or the CRM
        sent a new one): drop the old coordinates and verification (even a
        VERIFIED one — the old point no longer describes this address) and
        verify the new address. With ``verify=False`` the location is left
        UNVERIFIED for the caller (or the background sweep) to geocode."""
        location = self._get_or_create_primary(company_id)
        location.address_line_1 = address_line_1
        location.address_line_2 = None
        location.city = city
        location.state = state
        location.postal_code = postal_code
        location.country = country or "USA"
        location.latitude = None
        location.longitude = None
        location.geom = None
        location.formatted_address = None
        location.provider = None
        location.provider_place_id = None
        location.search_query = None
        location.confidence = None
        location.source = LocationSource.USER_PROVIDED
        location.verification_status = VerificationStatus.UNVERIFIED
        location.verification_notes = None
        location.verified_at = None
        location.geocode_attempts = 0
        location.last_geocode_attempt_at = None
        self.db.flush()
        if not verify:
            return location

        return self.verify_or_flag(
            company_id=company_id,
            company_name=company_name,
            raw_address=address_line_1,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
        ) or location

    def apply_candidate(
        self,
        *,
        company_id,
        candidate: LocationCandidate,
        search_query: str,
        source: LocationSource = LocationSource.VERIFIED_BUSINESS,
    ) -> Location:
        """Persist a specific candidate a human selected from an ambiguous result set."""
        return self._persist_verified_location(
            company_id=company_id, candidate=candidate, search_query=search_query, source=source
        )

    def _persist_verified_location(
        self,
        *,
        company_id,
        candidate: LocationCandidate,
        search_query: str,
        source: LocationSource,
    ) -> Location:
        existing = (
            self.db.query(Location)
            .filter(Location.company_id == company_id, Location.is_primary.is_(True))
            .first()
        )
        location = existing or Location(company_id=company_id, is_primary=True)

        location.address_line_1 = candidate.address_line_1
        location.address_line_2 = candidate.address_line_2
        location.city = candidate.city
        location.state = candidate.state
        location.postal_code = candidate.postal_code
        location.country = candidate.country or "USA"
        location.latitude = candidate.latitude
        location.longitude = candidate.longitude
        location.geom = from_shape(Point(candidate.longitude, candidate.latitude), srid=4326)
        location.formatted_address = candidate.formatted_address
        location.source = source
        location.provider = self.provider.name
        location.provider_place_id = candidate.place_id
        location.search_query = search_query
        location.confidence = candidate.confidence
        location.verification_status = VerificationStatus.VERIFIED
        location.verification_notes = None
        location.verified_at = datetime.now(timezone.utc)

        if existing is None:
            self.db.add(location)
        self.db.flush()
        return location

    def mark_needs_verification(
        self,
        *,
        company_id,
        raw_address: str | None,
        notes: str | None = None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country: str | None = None,
    ) -> Location:
        location = self._get_or_create_primary(company_id)
        location.source = LocationSource.NEEDS_VERIFICATION
        location.verification_status = VerificationStatus.NEEDS_REVIEW
        location.verification_notes = notes
        self._apply_imported_fields(location, raw_address, city, state, postal_code, country)
        self.db.flush()
        return location

    def mark_failed(
        self,
        *,
        company_id,
        raw_address: str | None,
        notes: str,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country: str | None = None,
    ) -> Location:
        location = self._get_or_create_primary(company_id)
        location.verification_status = VerificationStatus.FAILED
        location.verification_notes = notes
        self._apply_imported_fields(location, raw_address, city, state, postal_code, country)
        self.db.flush()
        return location

    def _get_primary(self, company_id) -> Location | None:
        return (
            self.db.query(Location)
            .filter(Location.company_id == company_id, Location.is_primary.is_(True))
            .first()
        )

    def _get_or_create_primary(self, company_id) -> Location:
        existing = self._get_primary(company_id)
        location = existing or Location(company_id=company_id, is_primary=True)
        if existing is None:
            self.db.add(location)
            # Flush now: sessions run with autoflush off, so a later
            # _get_primary in the same unit of work wouldn't see this row
            # and a second primary location would be created.
            self.db.flush()
        return location

    @staticmethod
    def _apply_imported_fields(
        location: Location,
        raw_address: str | None,
        city: str | None,
        state: str | None,
        postal_code: str | None,
        country: str | None,
    ) -> None:
        """Preserve whatever the importer already knew about this address
        even when verification didn't succeed — never overwrite with a
        fabricated value, but don't discard real imported data either."""
        if raw_address:
            location.address_line_1 = raw_address
        if city:
            location.city = city
        if state:
            location.state = state
        if postal_code:
            location.postal_code = postal_code
        if country:
            location.country = country
