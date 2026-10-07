"""Bigin sync: initial/incremental sync, matching & dedup, address changes ->
geocoding, deletions, failures, admin API and the notification webhook.
Bigin and the geocoder are faked — no network."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models.company import Company
from app.models.contact import Contact
from app.models.crm_sync import BiginSyncRun, SyncRunStatus, SyncTrigger
from app.models.location import Location, VerificationStatus
from app.services import background, bigin as bigin_module
from app.services.bigin import BiginClient, BiginError
from app.services.bigin_sync import BiginSyncService, get_state
from app.tests.test_address_verification import NASH_ST, WILSON_EYE, FakeProvider


def _ts(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


def account(id_, name="Wilson Eye Associates", street="2402 Montgomery Dr SW", minutes_ago=60, **extra):
    return {
        "id": id_, "Account_Name": name, "Phone": "(252) 555-0100", "Website": "wilsoneye.example",
        "Billing_Street": street, "Billing_City": "Wilson", "Billing_State": "NC", "Billing_Code": "27893",
        "Billing_Country": "United States", "Owner": {"id": "u1", "name": "Dana Owner", "email": "dana@sam.example"},
        "Modified_Time": _ts(minutes_ago), **extra,
    }


def contact(id_, account_id, email="jane@wilsoneye.example", minutes_ago=60, **extra):
    return {
        "id": id_, "First_Name": "Jane", "Last_Name": "Doe", "Email": email, "Phone": "252-555-0111",
        "Title": "Practice Manager", "Account_Name": {"id": account_id, "name": "x"},
        "Owner": {"id": "u1", "name": "Dana Owner"}, "Modified_Time": _ts(minutes_ago), **extra,
    }


class FakeBigin:
    is_configured = True

    def __init__(self):
        self.records = {"Accounts": [], "Contacts": []}
        self.deleted = {"Accounts": [], "Contacts": []}
        self.calls = []
        self.fail_with = None
        self.watch_calls = []

    def iter_records(self, module, fields, *, modified_after=None):
        self.calls.append((module, modified_after))
        if self.fail_with:
            raise self.fail_with
        for r in sorted(self.records[module], key=lambda r: r["Modified_Time"], reverse=True):
            if modified_after and datetime.fromisoformat(r["Modified_Time"]) <= modified_after:
                return
            yield r

    def iter_deleted(self, module, max_pages=10):
        return iter(self.deleted[module])

    def check_connection(self):
        if self.fail_with:
            raise self.fail_with

    def enable_notifications(self, **kwargs):
        self.watch_calls.append(kwargs)

    def disable_notifications(self, channel_id):
        pass


@pytest.fixture
def bigin():
    fake = FakeBigin()
    bigin_module.set_bigin_client(fake)
    yield fake
    bigin_module.set_bigin_client(None)


@pytest.fixture
def geo():
    return FakeProvider(by_street={"2402 Montgomery Dr SW": WILSON_EYE, "2250 Nash St N": NASH_ST})


def sync(db, bigin, geo, *, full=False, trigger=SyncTrigger.MANUAL):
    service = BiginSyncService(db, bigin, geo)
    run = service.start_run(trigger=trigger, full=full)
    return service.execute(run)


def _primary(db, company):
    return db.query(Location).filter(Location.company_id == company.id, Location.is_primary.is_(True)).one()


# ------------------------------------------------------------------- sync


def test_initial_sync_imports_companies_contacts_and_geocodes(db, bigin, geo):
    bigin.records["Accounts"] = [account("A1"), account("A2", name="No Address Co", street=None,
                                                          Billing_City=None, Billing_State=None, Billing_Code=None)]
    bigin.records["Contacts"] = [contact("C1", "A1"), contact("C2", "UNKNOWN")]

    run = sync(db, bigin, geo)

    assert run.status == SyncRunStatus.SUCCESS and run.full is True
    assert (run.companies_created, run.contacts_created, run.records_skipped) == (2, 1, 1)
    assert bigin.calls[0] == ("Accounts", None)  # first sync reads everything
    wilson = db.query(Company).filter(Company.bigin_account_id == "A1").one()
    assert wilson.crm_owner_name == "Dana Owner" and wilson.domain == "wilsoneye.example"
    loc = _primary(db, wilson)
    assert loc.verification_status == VerificationStatus.VERIFIED
    assert (loc.latitude, loc.longitude) == (WILSON_EYE.latitude, WILSON_EYE.longitude)
    assert run.locations_verified == 1
    jane = db.query(Contact).filter(Contact.bigin_contact_id == "C1").one()
    assert jane.company_id == wilson.id and jane.full_name == "Jane Doe" and jane.source == "bigin"
    state = get_state(db)
    assert state.connection_ok and state.last_full_sync_at and state.accounts_watermark


def test_incremental_sync_updates_only_changes_and_skips_unchanged_geocoding(db, bigin, geo):
    bigin.records["Accounts"] = [account("A1", minutes_ago=600)]
    bigin.records["Contacts"] = [contact("C1", "A1", minutes_ago=600)]
    sync(db, bigin, geo)
    geo.structured_calls.clear()

    # Phone + owner changed in Bigin; address unchanged.
    bigin.records["Accounts"] = [account("A1", Phone="252-555-0199", Owner={"id": "u2", "name": "New Owner"}, minutes_ago=1)]
    bigin.records["Contacts"] = [contact("C1", "A1", email="jane.doe@wilsoneye.example", minutes_ago=1)]
    run = sync(db, bigin, geo)

    assert bigin.calls[-2][1] is not None  # incremental: modified_after watermark
    assert (run.companies_updated, run.contacts_updated, run.companies_created) == (1, 1, 0)
    company = db.query(Company).filter(Company.bigin_account_id == "A1").one()
    assert company.phone == "252-555-0199" and company.phone_normalized and company.crm_owner_name == "New Owner"
    assert db.query(Contact).filter(Contact.bigin_contact_id == "C1").one().email == "jane.doe@wilsoneye.example"
    assert geo.structured_calls == []  # unchanged address is never re-geocoded
    assert run.addresses_changed == 0


def test_changed_address_replaces_coordinates(db, bigin, geo):
    bigin.records["Accounts"] = [account("A1", minutes_ago=600)]
    sync(db, bigin, geo)
    bigin.records["Accounts"] = [account("A1", street="2250 Nash St N", Billing_Code="27896", minutes_ago=1)]

    run = sync(db, bigin, geo)

    company = db.query(Company).filter(Company.bigin_account_id == "A1").one()
    loc = _primary(db, company)
    assert run.addresses_changed == 1
    assert loc.address_line_1 == NASH_ST.address_line_1 and loc.latitude == NASH_ST.latitude
    assert loc.verification_status == VerificationStatus.VERIFIED


def test_unresolvable_address_needs_review_without_invented_coordinates(db, bigin, geo):
    bigin.records["Accounts"] = [account("A9", street="1 Nowhere Rd")]
    run = sync(db, bigin, geo)
    loc = _primary(db, db.query(Company).filter(Company.bigin_account_id == "A9").one())
    assert loc.verification_status == VerificationStatus.NEEDS_REVIEW
    assert loc.latitude is None and loc.longitude is None
    assert run.locations_needs_review == 1


def test_duplicate_detection_links_existing_rows_by_phone_and_email(db, bigin, geo):
    existing = Company(name="Wilson Eye Assoc. (imported)", normalized_name="x", phone="252.555.0100",
                       phone_normalized="2525550100", website="https://intranet.local/manual")
    db.add(existing)
    db.flush()
    db.add(Contact(company_id=existing.id, first_name="J", email="JANE@wilsoneye.example", source="import"))
    db.flush()
    bigin.records["Accounts"] = [account("A1", Website=None)]
    bigin.records["Contacts"] = [contact("C1", "A1")]

    run = sync(db, bigin, geo)

    assert run.companies_created == 0 and run.contacts_created == 0
    db.refresh(existing)
    assert existing.bigin_account_id == "A1" and existing.name == "Wilson Eye Associates"
    assert existing.website == "https://intranet.local/manual"  # a Bigin blank never wipes local data on first link
    assert db.query(Contact).filter(Contact.company_id == existing.id).count() == 1
    assert db.query(Contact).filter(Contact.company_id == existing.id).one().bigin_contact_id == "C1"


def test_name_alone_is_never_used_to_match(db, bigin, geo):
    db.add(Company(name="Wilson Eye Associates", normalized_name="wilson eye associates"))
    db.flush()
    bigin.records["Accounts"] = [account("A1", Phone=None, Website=None)]
    run = sync(db, bigin, geo)
    assert run.companies_created == 1
    assert db.query(Company).filter(Company.name == "Wilson Eye Associates").count() == 2


def test_deleted_records_are_archived_and_hidden_from_prospects(db, bigin, geo, admin_client):
    bigin.records["Accounts"] = [account("A1")]
    bigin.records["Contacts"] = [contact("C1", "A1")]
    sync(db, bigin, geo)
    bigin.deleted["Accounts"] = [{"id": "A1", "deleted_time": _ts(1)}]
    run = sync(db, bigin, geo)

    company = db.query(Company).filter(Company.bigin_account_id == "A1").one()
    assert run.records_deleted == 1 and company.crm_deleted_at is not None
    names = [p["company_name"] for p in admin_client.get("/prospects").json()["items"]]
    assert "Wilson Eye Associates" not in names
    assert admin_client.get(f"/companies/{company.id}").status_code == 200  # history kept


def test_failed_api_request_marks_run_failed_and_disconnected(db, bigin, geo):
    bigin.fail_with = BiginError("auth_failed", "Zoho rejected the Bigin credentials (invalid_code).")
    run = sync(db, bigin, geo)
    assert run.status == SyncRunStatus.FAILED and "invalid_code" in run.message
    state = get_state(db)
    assert state.connection_ok is False and state.last_success_at is None


def test_one_bad_record_does_not_sink_the_sync(db, bigin, geo):
    bigin.records["Accounts"] = [account("A1"), {"id": "A2", "Account_Name": None, "Modified_Time": _ts(5)}]
    run = sync(db, bigin, geo)
    assert run.status == SyncRunStatus.PARTIAL and run.companies_created == 1
    assert run.errors and run.errors[0]["bigin_id"] == "A2"


# ------------------------------------------------------------------ client


def test_client_refreshes_token_and_paginates():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": f"tok{len(calls)}", "expires_in": 3600})
        assert request.headers["Authorization"].startswith("Zoho-oauthtoken ")
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(200, json={"data": [{"id": "1"}], "info": {"more_records": True}})
        return httpx.Response(200, json={"data": [{"id": "2"}], "info": {"more_records": False}})

    client = BiginClient(httpx.Client(transport=httpx.MockTransport(handler)))
    client.client_id, client.client_secret, client.refresh_token = "id", "secret", "refresh"
    assert [r["id"] for r in client.iter_records("Accounts", ["Account_Name"])] == ["1", "2"]
    assert sum(1 for c in calls if c.url.path == "/oauth/v2/token") == 1  # token cached


def test_client_reports_bad_refresh_token_without_leaking_secret():
    def handler(request):
        return httpx.Response(200, json={"error": "invalid_code"})

    client = BiginClient(httpx.Client(transport=httpx.MockTransport(handler)))
    client.client_id, client.client_secret, client.refresh_token = "id", "s3cr3t", "r3fr3sh"
    with pytest.raises(BiginError) as err:
        client.check_connection()
    assert err.value.code == "auth_failed"
    assert "s3cr3t" not in str(err.value) and "r3fr3sh" not in str(err.value)


# --------------------------------------------------------------------- API


def test_status_and_manual_sync_api(admin_client, sales_client, bigin, monkeypatch):
    submitted = []
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: submitted.append((fn, a, k)))

    assert sales_client.get("/crm-sync/status").status_code == 403
    status = admin_client.get("/crm-sync/status").json()
    assert status["connection"] == {**status["connection"], "configured": True, "ok": True}

    res = admin_client.post("/crm-sync/run", json={"full": True})
    assert res.status_code == 202 and res.json()["status"] == "running"
    assert submitted and submitted[0][1][0] is not None  # job queued with the run id
    assert admin_client.post("/crm-sync/run").status_code == 409  # one sync at a time
    assert len(admin_client.get("/crm-sync/runs").json()) == 1


def test_sync_refused_when_bigin_not_configured(admin_client):
    bigin_module.set_bigin_client(None)
    res = admin_client.get("/crm-sync/status").json()
    assert res["connection"]["configured"] is False and res["connection"]["ok"] is False
    run = admin_client.post("/crm-sync/run")
    assert run.status_code == 400 and run.json()["detail"]["code"] == "bigin_not_configured"


def test_scheduled_sync_renews_notification_channel(db, bigin, geo, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "public_api_base_url", "https://api.example.com")
    service = BiginSyncService(db, bigin, geo)
    service.ensure_notification_channel()
    state = get_state(db)
    assert bigin.watch_calls[0]["notify_url"] == "https://api.example.com/integrations/bigin/notifications"
    assert state.channel_token and state.channel_expires_at - datetime.now(timezone.utc) <= timedelta(days=1)
    service.ensure_notification_channel()
    assert len(bigin.watch_calls) == 1  # still valid — not renewed


def test_webhook_rejects_bad_token_and_handles_delete(app, db, bigin, geo, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(background, "submit", lambda *a, **k: None)
    bigin.records["Accounts"] = [account("A1")]
    sync(db, bigin, geo)
    state = get_state(db)
    state.channel_id, state.channel_token = "1001", "secret-token"
    db.commit()
    client = TestClient(app)

    bad = client.post("/integrations/bigin/notifications", json={"channel_id": "1001", "token": "nope"})
    assert bad.status_code == 403
    ok = client.post("/integrations/bigin/notifications", json={
        "channel_id": "1001", "token": "secret-token", "module": "Accounts", "ids": ["A1"], "operation": "delete",
    })
    assert ok.status_code == 200
    assert db.query(Company).filter(Company.bigin_account_id == "A1").one().crm_deleted_at is not None


def test_unexpected_error_closes_run_as_failed(db, bigin, geo):
    bigin.fail_with = RuntimeError("database went away")
    service = BiginSyncService(db, bigin, geo)
    run = service.start_run(trigger=SyncTrigger.SCHEDULED)
    with pytest.raises(RuntimeError):
        service.execute(run)
    assert run.status == SyncRunStatus.FAILED and run.finished_at is not None
