import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ResearchStatus(str, enum.Enum):
    PENDING = "pending"  # queued, nothing gathered yet
    RESEARCHING = "researching"  # gathering sources
    SUMMARIZING = "summarizing"  # sources gathered, LLM synthesis running
    COMPLETED = "completed"
    FAILED = "failed"


class CompanyResearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The business overview for one company.

    research_data is the structured input the summary was generated from
    (kept so the summary can be regenerated without re-crawling, and so it
    can be audited); summary_data is the structured LLM output, where every
    claim names the source ids it rests on.
    """

    __tablename__ = "company_research"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus, name="research_status"), nullable=False, default=ResearchStatus.PENDING
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sam_it_relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "high" | "medium" | "low" — how well the sources support the summary.
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    research_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    researched_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sources: Mapped[list["CompanyResearchSource"]] = relationship(
        "CompanyResearchSource",
        back_populates="research",
        cascade="all, delete-orphan",
        order_by="CompanyResearchSource.ref",
    )


class CompanyResearchSource(UUIDPrimaryKeyMixin, Base):
    """One piece of evidence the summary may cite (a fetched web page, the
    CRM record, the verified location)."""

    __tablename__ = "company_research_sources"

    research_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_research.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Short id the LLM cites ("S1", "S2", ...). Stable within one research run.
    ref: Mapped[str] = mapped_column(String(10), nullable=False)
    # "website" | "crm" | "location"
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fetched_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    research: Mapped["CompanyResearch"] = relationship("CompanyResearch", back_populates="sources")
