import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ContactType(str, enum.Enum):
    DECISION_MAKER = "decision_maker"
    INFLUENCER = "influencer"
    GATEKEEPER = "gatekeeper"
    UNKNOWN = "unknown"


class ContactVerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    IMPORTED = "imported"
    VERIFIED = "verified"


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_type: Mapped[ContactType] = mapped_column(
        Enum(ContactType, name="contact_type"), nullable=False, default=ContactType.UNKNOWN
    )
    verification_status: Mapped[ContactVerificationStatus] = mapped_column(
        Enum(ContactVerificationStatus, name="contact_verification_status"),
        nullable=False,
        default=ContactVerificationStatus.IMPORTED,
    )
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="contacts")
