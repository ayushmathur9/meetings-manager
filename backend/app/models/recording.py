import enum
import uuid

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RecordingStatus(str, enum.Enum):
    # RECORDING happens entirely in the browser; the row is created once the
    # upload starts.
    UPLOADING = "uploading"
    PROCESSING = "processing"  # stored; transcription submitted / running
    COMPLETED = "completed"
    FAILED = "failed"


class MeetingRecording(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audio of a meeting. The audio itself lives in object storage under
    storage_key (never in Postgres) and is only reachable through
    authenticated, short-lived URLs."""

    __tablename__ = "meeting_recordings"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RecordingStatus] = mapped_column(
        Enum(RecordingStatus, name="recording_status"), nullable=False, default=RecordingStatus.UPLOADING
    )
    storage_backend: Mapped[str | None] = mapped_column(String(20), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Measured in the browser while recording (pauses excluded); replaced by
    # the provider's measured duration once transcribed.
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    uploaded_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting: Mapped["Meeting"] = relationship("Meeting")
    created_by: Mapped["User | None"] = relationship("User")
    transcript: Mapped["MeetingTranscript | None"] = relationship(
        "MeetingTranscript", back_populates="recording", uselist=False, cascade="all, delete-orphan"
    )


class MeetingTranscript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provider-neutral transcript of one recording. Kept separate from the
    recording so later features (meeting summary, action items, CRM notes)
    can hang off it without touching audio handling."""

    __tablename__ = "meeting_transcripts"

    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meeting_recordings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"speaker": "1", "start": 0.0, "end": 4.2, "text": "..."}] — seconds;
    # speakers are anonymous labels, never guessed names.
    segments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    speaker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    recording: Mapped["MeetingRecording"] = relationship("MeetingRecording", back_populates="transcript")
