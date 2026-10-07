import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class ProspectPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Prospect(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "prospects"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Sales priority — influences which meetings the day planner keeps when
    # not everything fits in working hours (see services/route_optimizer.py).
    priority: Mapped[ProspectPriority] = mapped_column(
        Enum(ProspectPriority, name="prospect_priority"),
        nullable=False,
        default=ProspectPriority.MEDIUM,
        server_default=ProspectPriority.MEDIUM.name,
    )
    assigned_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company", back_populates="prospect")
    assigned_user: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_user_id])
    assigned_by: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_by_id])
