import enum
import uuid
from datetime import date, time

from sqlalchemy import Boolean, Date, Enum, Float, ForeignKey, Index, Integer, String, Time
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
    __table_args__ = (Index("ix_routes_salesperson_date", "salesperson_id", "date"),)

    salesperson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_location: Mapped[dict] = mapped_column(JSONB, nullable=False)
    end_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[RouteStatus] = mapped_column(
        Enum(RouteStatus, name="route_status"), nullable=False, default=RouteStatus.DRAFT
    )
    # Total road distance / total driving time (including the leg to the end location).
    estimated_distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Sales-day planner configuration (null for routes built by the legacy endpoints)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # same_as_start|custom|none
    radius_miles: Mapped[float | None] = mapped_column(Float, nullable=True)
    working_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    working_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    meeting_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    travel_buffer_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_overtime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # --- Computed plan snapshot (so a saved route reopens exactly as it was planned)
    total_meeting_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_travel_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # MultiLineString coords
    unscheduled: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    optimization_engine: Mapped[str | None] = mapped_column(String(50), nullable=True)

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
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    # arrival_time = arrival at the stop; departure_time = meeting end / leaving the stop.
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    departure_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    meeting_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    meeting_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wait_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Travel/distance from the previous stop (or the start location).
    travel_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_fixed_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    outside_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Snapshot of where/what the stop was when the route was saved — used to
    # detect when the underlying company location changed since.
    company_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    route: Mapped["Route"] = relationship("Route", back_populates="stops")
    meeting: Mapped["Meeting | None"] = relationship("Meeting", back_populates="route_stop")
    company: Mapped["Company | None"] = relationship("Company")
    location: Mapped["Location | None"] = relationship("Location")
