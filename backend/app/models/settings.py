from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OrgSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Singleton row holding org-wide configuration."""

    __tablename__ = "org_settings"

    org_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Sam IT Solutions")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    default_meeting_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    default_travel_buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    working_hours_start: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    working_hours_end: Mapped[str] = mapped_column(String(5), nullable=False, default="17:00")

    default_start_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    saved_locations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
