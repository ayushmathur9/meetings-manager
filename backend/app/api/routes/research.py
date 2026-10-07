import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.company import Company
from app.models.company_research import CompanyResearch, ResearchStatus
from app.models.user import User
from app.services import background
from app.services.activity_service import ActivityService
from app.services.business_summary import BusinessSummaryService, run_research_job

router = APIRouter(prefix="/companies/{company_id}/research", tags=["research"])


class ResearchSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ref: str
    source_type: str
    url: str | None
    title: str | None
    fetched_at: datetime | None


class ResearchOut(BaseModel):
    status: ResearchStatus | None  # None: never researched
    summary: str | None = None
    sam_it_relevance: str | None = None
    industry: str | None = None
    confidence: str | None = None
    summary_data: dict | None = None
    sources: list[ResearchSourceOut] = []
    generated_at: datetime | None = None
    researched_at: datetime | None = None
    is_stale: bool = False
    error: str | None = None
    model: str | None = None


def _out(research: CompanyResearch | None) -> ResearchOut:
    if research is None:
        return ResearchOut(status=None)
    return ResearchOut(
        status=research.status,
        summary=research.summary,
        sam_it_relevance=research.sam_it_relevance,
        industry=research.industry,
        confidence=research.confidence,
        summary_data=research.summary_data,
        sources=[ResearchSourceOut.model_validate(s) for s in research.sources],
        generated_at=research.generated_at,
        researched_at=research.researched_at,
        is_stale=BusinessSummaryService.is_stale(research),
        error=research.error,
        model=research.model,
    )


def _company(db: Session, company_id: uuid.UUID) -> Company:
    company = db.query(Company).options(selectinload(Company.locations)).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


@router.get("", response_model=ResearchOut)
def get_research(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchOut:
    """The stored overview. Generation is queued automatically the first
    time a company is opened, when the overview is older than
    RESEARCH_STALE_DAYS, or when a previous run died mid-way."""
    company = _company(db, company_id)
    service = BusinessSummaryService(db)
    research = service.get(company.id)
    needs_run = (
        (research is None and get_settings().research_auto_generate)
        or (research is not None and research.status == ResearchStatus.COMPLETED and service.is_stale(research))
        or (research is not None and service.is_stuck(research))
    )
    if needs_run:
        research = service.request(company)
        db.commit()
        background.submit(run_research_job, research.id)
    return _out(research)


@router.post("/refresh", response_model=ResearchOut, status_code=status.HTTP_202_ACCEPTED)
def refresh_research(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchOut:
    company = _company(db, company_id)
    service = BusinessSummaryService(db)
    research = service.get(company.id)
    if research is not None and research.status in (ResearchStatus.RESEARCHING, ResearchStatus.SUMMARIZING) \
            and not service.is_stuck(research):
        return _out(research)  # already running — don't double-spend
    research = service.request(company, user_id=current_user.id)
    ActivityService(db).log(
        user_id=current_user.id, entity_type="company", entity_id=company.id, action="summary_refreshed"
    )
    db.commit()
    background.submit(run_research_job, research.id)
    return _out(research)
