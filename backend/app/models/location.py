import enum
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class LocationSource(str, enum.Enum):
    USER_PROVIDED = "user_provided"
    GEOCODED = "geocoded"
    VERIFIED_BUSINESS = "verified_business"
    NEEDS_VERIFICATION = "needs_verification"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    FAILED = "failed"


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "locations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    address_line_1: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, default="USA")

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    formatted_address: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    source: Mapped[LocationSource] = mapped_column(
        Enum(LocationSource, name="location_source"),
        nullable=False,
        default=LocationSource.NEEDS_VERIFICATION,
    )
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    search_query: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
    )
    verification_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    verified_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="locations")
