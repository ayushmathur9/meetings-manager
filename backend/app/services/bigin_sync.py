"""Bigin -> Meetings Manager synchronization.

Bigin is the source of truth for CRM data (names, phones, websites,
addresses, owners); Meetings Manager keeps a local copy so search, the map,
routing and meetings never depend on Bigin being reachable.

Matching
  * Records are matched on their Bigin id (``bigin_account_id`` /
    ``bigin_contact_id``) — never on name.
  * Only a record with no linked local row falls back to secondary
    deduplication, and only on an unambiguous match: companies by
    normalized phone or website domain, contacts by email or phone within
    the same company. Anything ambiguous creates a new row instead of
    merging two businesses.

Overwrite rules
  * A company/contact already linked to Bigin mirrors Bigin exactly.
  * An existing local row being linked for the first time is only filled
    in — Bigin blanks never wipe data someone entered locally.
  * An empty Bigin address never clears a local address (it would knock
    the company off the map with nothing to replace it).

Locations
  A new or changed address replaces the primary location's coordinates and
  verification, and is geocoded right after the sync (up to
  BIGIN_GEOCODE_BATCH_SIZE per run; the location sweep handles the rest).
  Unchanged addresses are never re-geocoded.

Triggers
  * Manual ("Sync Now"), the periodic reconciliation, and Bigin instant
    notifications all run the same incremental sync (records modified since
    the stored watermark, with a 10-minute overlap). The first sync, or a
    manual "full" sync, reads everything.
  * Deletions: notifications mark records deleted immediately; every sync
    also reads Bigin's deleted-records list so a missed notification can't
    leave a deleted record live forever. Deleted records are archived
    (``crm_deleted_at``), not removed — meetings and recordings stay intact.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.company import Company, CompanyStatus
from app.models.contact import Contact, ContactVerificationStatus
from app.models.crm_sync import BiginSyncRun, BiginSyncState, SyncRunStatus, SyncTrigger
from app.models.location import Location, VerificationStatus
from app.providers.location import get_geocoding_provider
from app.providers.location.base import LocationProvider
from app.services.bigin import BiginClient, BiginError, get_bigin_client, parse_bigin_datetime
from app.services.location_service import LocationService
from app.services.normalization import extract_domain, normalize_company_name, normalize_phone

logger = logging.getLogger("app.bigin_sync")

ACCOUNT_FIELDS = [
    "Account_Name", "Phone", "Website", "Billing_Street", "Billing_City", "Billing_State",
    "Billing_Code", "Billing_Country", "Owner", "Modified_Time",
]
CONTACT_FIELDS = [
    "First_Name", "Last_Name", "Email", "Phone", "Mobile", "Title", "Account_Name", "Owner", "Modified_Time",
]
NOTIFICATION_EVENTS = ["Accounts.all", "Contacts.all"]

WATERMARK_OVERLAP = timedelta(minutes=10)
STALE_RUN_AFTER = timedelta(hours=2)
CHANNEL_LIFETIME = timedelta(hours=23)  # Bigin caps channels at one day
CHANNEL_RENEW_BEFORE = timedelta(hours=3)
MAX_LOGGED_ERRORS = 50
SYNC_LOCK_KEY = 0xB1612C  # pg advisory lock: one sync at a time across replicas

_COUNTRY_ALIASES = {"us": "usa", "u.s.": "usa", "u.s.a.": "usa", "united states": "usa", "united states of america": "usa"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().replace(",", " ").split())


def _norm_country(value: str | None) -> str:
    key = _norm(value)
    return _COUNTRY_ALIASES.get(key, key)


def get_state(db: Session) -> BiginSyncState:
    state = db.query(BiginSyncState).first()
    if state is None:
        state = BiginSyncState(connection_ok=False)
        db.add(state)
        db.flush()
    return state


@dataclass
class _Tally:
    companies_created: int = 0
    companies_updated: int = 0
    contacts_created: int = 0
    contacts_updated: int = 0
    records_deleted: int = 0
    records_skipped: int = 0
    addresses_changed: int = 0
    errors: list[dict] = field(default_factory=list)
    geocode_company_ids: list = field(default_factory=list)

    def error(self, module: str, bigin_id, message: str) -> None:
        if len(self.errors) < MAX_LOGGED_ERRORS:
            self.errors.append({"module": module, "bigin_id": str(bigin_id) if bigin_id else None, "error": message[:500]})


class BiginSyncService:
    def __init__(
        self, db: Session, client: BiginClient | None = None, location_provider: LocationProvider | None = None
    ) -> None:
        self.db = db
        self.client = client or get_bigin_client()
        self._location_provider = location_provider
        self.settings = get_settings()

    # ================================================================ run
    def start_run(self, *, trigger: SyncTrigger, full: bool = False, user_id=None) -> BiginSyncRun:
        run = BiginSyncRun(trigger=trigger, full=full, status=SyncRunStatus.RUNNING, triggered_by_id=user_id)
        self.db.add(run)
        self.db.flush()
        return run

    def execute(self, run: BiginSyncRun) -> BiginSyncRun:
        """Run the sync recorded by ``run`` to completion. Never raises for a
        Bigin problem — the run is marked FAILED with the reason instead."""
        state = get_state(self.db)
        state.last_attempt_at = _now()
        self.db.commit()

        tally = _Tally()
        full = run.full or state.last_full_sync_at is None
        run.full = full
        try:
            accounts_since = None if full or state.accounts_watermark is None else state.accounts_watermark - WATERMARK_OVERLAP
            contacts_since = None if full or state.contacts_watermark is None else state.contacts_watermark - WATERMARK_OVERLAP

            newest = self._sync_module("Accounts", ACCOUNT_FIELDS, accounts_since, self._upsert_account, tally)
            if newest and (state.accounts_watermark is None or newest > state.accounts_watermark):
                state.accounts_watermark = newest
            self.db.commit()

            newest = self._sync_module("Contacts", CONTACT_FIELDS, contacts_since, self._upsert_contact, tally)
            if newest and (state.contacts_watermark is None or newest > state.contacts_watermark):
                state.contacts_watermark = newest
            self.db.commit()

            self._sync_deletions(tally)
            self.db.commit()
        except BiginError as exc:
            self.db.rollback()
            self._finish(run, state, tally, SyncRunStatus.FAILED, exc.user_message)
            if exc.code in ("auth_failed", "not_configured", "permission_denied"):
                state.connection_ok = False
                state.connection_error = exc.user_message
                state.connection_checked_at = _now()
            self.db.commit()
            return run
        except Exception:
            # Not a Bigin problem (e.g. a database error): close the run as
            # failed instead of leaving it "running", then surface the bug.
            logger.exception("Bigin sync crashed")
            self.db.rollback()
            self._finish(run, state, tally, SyncRunStatus.FAILED, "Sync failed with an internal error — see server logs.")
            self.db.commit()
            raise

        verified, needs_review = self._geocode(tally.geocode_company_ids)
        run.locations_verified = verified
        run.locations_needs_review = needs_review

        now = _now()
        state.connection_ok = True
        state.connection_error = None
        state.connection_checked_at = now
        state.last_success_at = now
        if full:
            state.last_full_sync_at = now
        status = SyncRunStatus.PARTIAL if tally.errors else SyncRunStatus.SUCCESS
        message = f"{len(tally.errors)} record(s) could not be synced" if tally.errors else None
        self._finish(run, state, tally, status, message)
        self.db.commit()
        return run

    def _finish(self, run, state, tally: _Tally, status: SyncRunStatus, message: str | None) -> None:
        run.status = status
        run.finished_at = _now()
        run.message = message
        run.errors = tally.errors or None
        for name in ("companies_created", "companies_updated", "contacts_created", "contacts_updated",
                     "records_deleted", "records_skipped", "addresses_changed"):
            setattr(run, name, getattr(tally, name))
        state.last_error = message if status == SyncRunStatus.FAILED else None
        self.db.add(run)

    def _sync_module(self, module, fields, since, upsert, tally: _Tally) -> datetime | None:
        newest: datetime | None = None
        for i, record in enumerate(self.client.iter_records(module, fields, modified_after=since), start=1):
            modified = parse_bigin_datetime(record.get("Modified_Time"))
            if modified and (newest is None or modified > newest):
                newest = modified
            savepoint = self.db.begin_nested()
            try:
                upsert(record, tally)
                savepoint.commit()
            except Exception as exc:  # one bad record must not sink the sync
                savepoint.rollback()
                logger.exception("Bigin %s record %s failed to sync", module, record.get("id"))
                tally.error(module, record.get("id"), f"{type(exc).__name__}: {exc}")
            if i % 100 == 0:
                self.db.commit()
        return newest

    # ============================================================ accounts
    def _upsert_account(self, record: dict, tally: _Tally) -> None:
        bigin_id = _clean(record.get("id"))
        name = _clean(record.get("Account_Name"))
        if not bigin_id or not name:
            tally.records_skipped += 1
            tally.error("Accounts", bigin_id, "Record has no id or company name")
            return

        company = self.db.query(Company).filter(Company.bigin_account_id == bigin_id).first()
        created = False
        authoritative = company is not None  # already Bigin-managed: mirror exactly
        if company is None:
            company = self._match_company(record)
        if company is None:
            company = Company(name=name, normalized_name=normalize_company_name(name), status=CompanyStatus.NEW)
            self.db.add(company)
            created = True
            authoritative = True

        owner = record.get("Owner") if isinstance(record.get("Owner"), dict) else {}
        status_field = self.settings.bigin_account_status_field.strip()
        values = {
            "name": name,
            "phone": _clean(record.get("Phone")),
            "website": _clean(record.get("Website")),
            "crm_owner_id": _clean(owner.get("id")),
            "crm_owner_name": _clean(owner.get("name")),
            "crm_owner_email": _clean(owner.get("email")),
            "crm_status": _clean(record.get(status_field)) if status_field else None,
        }
        changed = created or company.bigin_account_id != bigin_id or company.crm_deleted_at is not None
        for attr, value in values.items():
            if value is None and not authoritative:
                continue
            if getattr(company, attr) != value:
                setattr(company, attr, value)
                changed = True
        company.normalized_name = normalize_company_name(company.name)
        company.domain = extract_domain(company.website)
        company.phone_normalized = normalize_phone(company.phone)
        company.bigin_account_id = bigin_id
        company.crm_modified_at = parse_bigin_datetime(record.get("Modified_Time"))
        company.crm_synced_at = _now()
        company.crm_deleted_at = None
        self.db.flush()

        if self._apply_address(company, record, tally):
            changed = True

        if created:
            tally.companies_created += 1
        elif changed:
            tally.companies_updated += 1

    def _match_company(self, record: dict) -> Company | None:
        """Secondary dedup for a Bigin account with no linked local row:
        exactly one unlinked company with the same phone or website domain."""
        unlinked = self.db.query(Company).filter(Company.bigin_account_id.is_(None))
        for column, value in (
            (Company.phone_normalized, normalize_phone(_clean(record.get("Phone")))),
            (Company.domain, extract_domain(_clean(record.get("Website")))),
        ):
            if not value:
                continue
            matches = unlinked.filter(column == value).limit(2).all()
            if len(matches) == 1:
                return matches[0]
        return None

    def _apply_address(self, company: Company, record: dict, tally: _Tally) -> bool:
        incoming = {
            "address_line_1": _clean(record.get("Billing_Street")),
            "city": _clean(record.get("Billing_City")),
            "state": _clean(record.get("Billing_State")),
            "postal_code": _clean(record.get("Billing_Code")),
            "country": _clean(record.get("Billing_Country")),
        }
        primary = (
            self.db.query(Location)
            .filter(Location.company_id == company.id, Location.is_primary.is_(True))
            .first()
        )
        if not any(incoming[k] for k in ("address_line_1", "city", "state", "postal_code")):
            return False

        if primary is not None and not self._address_differs(primary, incoming):
            # Same address. Geocode only if it was never attempted (e.g. it
            # arrived while no geocoder key was configured).
            if primary.latitude is None and primary.verification_status == VerificationStatus.UNVERIFIED:
                tally.geocode_company_ids.append(company.id)
            return False

        LocationService(self.db, self._provider()).replace_address(
            company_id=company.id, company_name=company.name, verify=False, **incoming
        )
        tally.addresses_changed += 1
        tally.geocode_company_ids.append(company.id)
        return True

    @staticmethod
    def _address_differs(location: Location, incoming: dict) -> bool:
        for key in ("address_line_1", "city", "state", "postal_code"):
            if _norm(getattr(location, key)) != _norm(incoming[key]):
                return True
        if incoming["country"] and location.country:
            return _norm_country(location.country) != _norm_country(incoming["country"])
        return False

    # ============================================================ contacts
    def _upsert_contact(self, record: dict, tally: _Tally) -> None:
        bigin_id = _clean(record.get("id"))
        if not bigin_id:
            tally.records_skipped += 1
            return
        account = record.get("Account_Name") if isinstance(record.get("Account_Name"), dict) else {}
        account_id = _clean(account.get("id"))
        company = (
            self.db.query(Company).filter(Company.bigin_account_id == account_id).first() if account_id else None
        )
        if company is None:
            # Contacts must belong to a company here; one with no (synced)
            # company in Bigin is skipped rather than parked on a fake one.
            tally.records_skipped += 1
            return

        contact = self.db.query(Contact).filter(Contact.bigin_contact_id == bigin_id).first()
        created = False
        authoritative = contact is not None
        if contact is None:
            contact = self._match_contact(company, record)
        if contact is None:
            contact = Contact(company_id=company.id, source="bigin", verification_status=ContactVerificationStatus.IMPORTED)
            self.db.add(contact)
            created = True
            authoritative = True

        first = _clean(record.get("First_Name"))
        last = _clean(record.get("Last_Name"))
        owner = record.get("Owner") if isinstance(record.get("Owner"), dict) else {}
        values = {
            "company_id": company.id,
            "first_name": first,
            "last_name": last,
            "full_name": " ".join(p for p in (first, last) if p) or None,
            "email": _clean(record.get("Email")),
            "phone": _clean(record.get("Phone")) or _clean(record.get("Mobile")),
            "title": _clean(record.get("Title")),
            "crm_owner_id": _clean(owner.get("id")),
            "crm_owner_name": _clean(owner.get("name")),
        }
        changed = created or contact.bigin_contact_id != bigin_id or contact.crm_deleted_at is not None
        for attr, value in values.items():
            if value is None and not authoritative:
                continue
            if getattr(contact, attr) != value:
                setattr(contact, attr, value)
                changed = True
        contact.bigin_contact_id = bigin_id
        contact.crm_modified_at = parse_bigin_datetime(record.get("Modified_Time"))
        contact.crm_synced_at = _now()
        contact.crm_deleted_at = None
        self.db.flush()

        if created:
            tally.contacts_created += 1
        elif changed:
            tally.contacts_updated += 1

    def _match_contact(self, company: Company, record: dict) -> Contact | None:
        unlinked = self.db.query(Contact).filter(
            Contact.company_id == company.id, Contact.bigin_contact_id.is_(None)
        )
        email = _clean(record.get("Email"))
        if email:
            matches = unlinked.filter(func.lower(Contact.email) == email.lower()).limit(2).all()
            if len(matches) == 1:
                return matches[0]
        for raw in (_clean(record.get("Phone")), _clean(record.get("Mobile"))):
            phone = normalize_phone(raw)
            if not phone:
                continue
            matches = [c for c in unlinked.filter(Contact.phone.isnot(None)).all() if normalize_phone(c.phone) == phone]
            if len(matches) == 1:
                return matches[0]
        return None

    # ============================================================ deletions
    def _sync_deletions(self, tally: _Tally) -> None:
        for module in ("Accounts", "Contacts"):
            ids = [str(r["id"]) for r in self.client.iter_deleted(module) if r.get("id")]
            tally.records_deleted += self.mark_deleted(module, ids)

    def mark_deleted(self, module: str, bigin_ids: list[str]) -> int:
        if not bigin_ids:
            return 0
        model, column = (Company, Company.bigin_account_id) if module == "Accounts" else (Contact, Contact.bigin_contact_id)
        rows = self.db.query(model).filter(column.in_(bigin_ids), model.crm_deleted_at.is_(None)).all()
        now = _now()
        for row in rows:
            row.crm_deleted_at = now
        self.db.flush()
        return len(rows)

    # ============================================================ geocoding
    def _provider(self) -> LocationProvider:
        if self._location_provider is None:
            self._location_provider = get_geocoding_provider()
        return self._location_provider

    def _geocode(self, company_ids: list) -> tuple[int, int]:
        """Verify addresses that are new/changed this run. Returns
        (verified, needs_review). Failures stay flagged for the sweep."""
        verified = needs_review = 0
        service = LocationService(self.db, self._provider())
        seen = set()
        for company_id in company_ids[: self.settings.bigin_geocode_batch_size]:
            if company_id in seen:
                continue
            seen.add(company_id)
            company = self.db.get(Company, company_id)
            primary = (
                self.db.query(Location)
                .filter(Location.company_id == company_id, Location.is_primary.is_(True))
                .first()
            )
            if company is None or primary is None:
                continue
            location = service.verify_or_flag(
                company_id=company.id,
                company_name=company.name,
                raw_address=primary.address_line_1,
                city=primary.city,
                state=primary.state,
                postal_code=primary.postal_code,
                country=primary.country,
            )
            self.db.commit()
            if location is None:
                continue
            if location.verification_status == VerificationStatus.VERIFIED:
                verified += 1
            elif location.verification_status in (VerificationStatus.NEEDS_REVIEW, VerificationStatus.FAILED):
                needs_review += 1
        return verified, needs_review

    # ========================================================= connection
    def check_connection(self) -> BiginSyncState:
        state = get_state(self.db)
        try:
            self.client.check_connection()
        except BiginError as exc:
            state.connection_ok = False
            state.connection_error = exc.user_message
        else:
            state.connection_ok = True
            state.connection_error = None
        state.connection_checked_at = _now()
        self.db.flush()
        return state

    # ======================================================= notifications
    def ensure_notification_channel(self) -> None:
        """Keep a Bigin instant-notification channel alive (they expire
        after at most a day). No-op unless a public URL is configured."""
        state = get_state(self.db)
        base = self.settings.public_api_base_url.rstrip("/")
        if not (self.settings.bigin_webhooks_enabled and base):
            return
        now = _now()
        if state.channel_id and state.channel_expires_at and state.channel_expires_at - now > CHANNEL_RENEW_BEFORE:
            return
        old_channel = state.channel_id
        channel_id = str(int(now.timestamp()))
        token = secrets.token_urlsafe(24)  # 32 chars; Bigin allows up to 50
        expires = now + CHANNEL_LIFETIME
        try:
            self.client.enable_notifications(
                channel_id=channel_id,
                token=token,
                notify_url=f"{base}/integrations/bigin/notifications",
                expires_at=expires,
                events=NOTIFICATION_EVENTS,
            )
        except BiginError as exc:
            state.channel_error = exc.user_message
            self.db.flush()
            return
        state.channel_id, state.channel_token, state.channel_expires_at = channel_id, token, expires
        state.channel_error = None
        self.db.flush()
        if old_channel:
            try:
                self.client.disable_notifications(old_channel)
            except BiginError:
                pass  # it expires on its own

    def verify_notification(self, channel_id: str | None, token: str | None) -> bool:
        state = get_state(self.db)
        if not (state.channel_id and state.channel_token and channel_id and token):
            return False
        return hmac.compare_digest(str(channel_id), state.channel_id) and hmac.compare_digest(
            str(token), state.channel_token
        )


# ============================================================ job entrypoints
_rerun_requested = threading.Event()


def latest_running_run(db: Session) -> BiginSyncRun | None:
    """The in-flight run, if any. A RUNNING row older than STALE_RUN_AFTER
    belongs to a process that died; it is closed as failed."""
    run = (
        db.query(BiginSyncRun)
        .filter(BiginSyncRun.status == SyncRunStatus.RUNNING)
        .order_by(BiginSyncRun.started_at.desc())
        .first()
    )
    if run is not None and _now() - run.started_at > STALE_RUN_AFTER:
        run.status = SyncRunStatus.FAILED
        run.finished_at = _now()
        run.message = "Sync was interrupted (server restarted) — it will be retried on the next run."
        db.flush()
        return None
    return run


def run_sync_job(run_id=None, *, trigger: SyncTrigger = SyncTrigger.SCHEDULED, full: bool = False) -> None:
    """Background entrypoint: execute a sync (an existing RUNNING row from
    "Sync Now", or a new one), holding the cross-replica sync lock. A sync
    requested while another is running is folded into one follow-up run."""
    from app.db.session import SessionLocal
    from app.services.background import advisory_lock

    with advisory_lock(SYNC_LOCK_KEY) as acquired:
        if not acquired:
            _rerun_requested.set()
            if run_id is not None:
                db = SessionLocal()
                try:
                    run = db.get(BiginSyncRun, run_id)
                    if run is not None and run.status == SyncRunStatus.RUNNING:
                        run.status = SyncRunStatus.FAILED
                        run.finished_at = _now()
                        run.message = "Another sync was already running; its results include this request."
                        db.commit()
                finally:
                    db.close()
            return
        while True:
            _rerun_requested.clear()
            db = SessionLocal()
            try:
                service = BiginSyncService(db)
                run = db.get(BiginSyncRun, run_id) if run_id else None
                if run is None:
                    run = service.start_run(trigger=trigger, full=full)
                    db.commit()
                service.execute(run)
                logger.info(
                    "Bigin sync %s (%s): +%d/~%d companies, +%d/~%d contacts, %d deleted",
                    run.status.value, run.trigger.value, run.companies_created, run.companies_updated,
                    run.contacts_created, run.contacts_updated, run.records_deleted,
                )
            finally:
                db.close()
            if not _rerun_requested.is_set():
                return
            run_id, trigger, full = None, SyncTrigger.WEBHOOK, False


def scheduled_sync() -> None:
    """Periodic reconciliation + notification-channel upkeep."""
    from app.db.session import SessionLocal

    client = get_bigin_client()
    if not client.is_configured:
        return
    db = SessionLocal()
    try:
        latest_running_run(db)
        service = BiginSyncService(db, client)
        service.ensure_notification_channel()
        db.commit()
    finally:
        db.close()
    run_sync_job(trigger=SyncTrigger.SCHEDULED)
