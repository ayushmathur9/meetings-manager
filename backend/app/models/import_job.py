import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ImportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportRowStatus(str, enum.Enum):
    VALID = "valid"
    DUPLICATE = "duplicate"
    ERROR = "error"
    IMPORTED = "imported"


class Import(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "imports"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    imported_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    column_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status"), nullable=False, default=ImportStatus.PENDING
    )
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    imported_by: Mapped["User"] = relationship("User")
    rows: Mapped[list["ImportRow"]] = relationship(
        "ImportRow", back_populates="import_job", cascade="all, delete-orphan"
    )


class ImportRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_rows"

    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("imports.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    mapped_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ImportRowStatus] = mapped_column(
        Enum(ImportRowStatus, name="import_row_status"), nullable=False
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )
    created_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )

    import_job: Mapped["Import"] = relationship("Import", back_populates="rows")
