import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BiginSyncState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Singleton row: sync watermark, connection health and the instant
    notification channel. Only services/bigin_sync.py writes it."""

    __tablename__ = "bigin_sync_state"

    # Highest Bigin Modified_Time seen per module — the next incremental sync
    # fetches records modified after it (minus a small overlap).
    accounts_watermark: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contacts_watermark: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_full_sync_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Result of the last real API call — the admin screen never claims
    # "Connected" from configuration alone.
    connection_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connection_checked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connection_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Bigin Notification API channel (expires after at most one day).
    channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_notification_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncRunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # finished, but some records failed
    FAILED = "failed"


class SyncTrigger(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"


class BiginSyncRun(UUIDPrimaryKeyMixin, Base):
    """One sync execution — the "Sync Logs" list."""

    __tablename__ = "bigin_sync_runs"

    trigger: Mapped[SyncTrigger] = mapped_column(Enum(SyncTrigger, name="sync_trigger"), nullable=False)
    full: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[SyncRunStatus] = mapped_column(
        Enum(SyncRunStatus, name="sync_run_status"), nullable=False, default=SyncRunStatus.RUNNING
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    companies_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    companies_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    addresses_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locations_verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locations_needs_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # [{"module": ..., "bigin_id": ..., "error": ...}] — capped in the service.
    errors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_by: Mapped["User | None"] = relationship("User")
