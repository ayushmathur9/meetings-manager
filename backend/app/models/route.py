import enum
import uuid
from datetime import date, time

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RouteStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Route(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "routes"

    salesperson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_location: Mapped[dict] = mapped_column(JSONB, nullable=False)
    end_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[RouteStatus] = mapped_column(
        Enum(RouteStatus, name="route_status"), nullable=False, default=RouteStatus.DRAFT
    )
    estimated_distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    salesperson: Mapped["User"] = relationship("User")
    stops: Mapped[list["RouteStop"]] = relationship(
        "RouteStop",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteStop.sequence",
    )


class RouteStop(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "route_stops"

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=False, unique=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    departure_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    travel_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    route: Mapped["Route"] = relationship("Route", back_populates="stops")
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="route_stop")
