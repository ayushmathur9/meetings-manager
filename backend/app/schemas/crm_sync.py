import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.crm_sync import SyncRunStatus, SyncTrigger


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: SyncTrigger
    full: bool
    status: SyncRunStatus
    started_at: datetime
    finished_at: datetime | None
    companies_created: int
    companies_updated: int
    contacts_created: int
    contacts_updated: int
    records_deleted: int
    records_skipped: int
    addresses_changed: int
    locations_verified: int
    locations_needs_review: int
    message: str | None
    triggered_by_name: str | None = None


class SyncRunDetail(SyncRunOut):
    errors: list[dict] | None


class SyncRunRequest(BaseModel):
    full: bool = False


class ConnectionStatus(BaseModel):
    configured: bool
    ok: bool
    checked_at: datetime | None
    error: str | None


class WebhookStatus(BaseModel):
    enabled: bool
    active: bool
    expires_at: datetime | None
    last_notification_at: datetime | None
    error: str | None


class SyncCounts(BaseModel):
    companies: int
    contacts: int
    locations: int  # synced companies with verified coordinates
    needs_review: int  # synced companies whose location needs a person
    archived: int  # deleted in Bigin, kept locally


class CrmSyncStatus(BaseModel):
    connection: ConnectionStatus
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_full_sync_at: datetime | None
    last_error: str | None
    next_sync_at: datetime | None
    interval_minutes: int
    running: SyncRunOut | None
    counts: SyncCounts
    webhooks: WebhookStatus
    recent_runs: list[SyncRunOut]
