import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CompanyStatus(str, enum.Enum):
    NEW = "new"
    RESEARCHED = "researched"
    CONTACTED = "contacted"
    MEETING = "meeting"
    FOLLOW_UP = "follow_up"
    NOT_INTERESTED = "not_interested"
    NOT_A_FIT = "not_a_fit"
    EXISTING_CUSTOMER = "existing_customer"


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[CompanyStatus] = mapped_column(
        Enum(CompanyStatus, name="company_status"), nullable=False, default=CompanyStatus.NEW
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("imports.id"), nullable=True
    )

    locations: Mapped[list["Location"]] = relationship(
        "Location", back_populates="company", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        "Contact", back_populates="company", cascade="all, delete-orphan"
    )
    prospect: Mapped["Prospect | None"] = relationship(
        "Prospect", back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
