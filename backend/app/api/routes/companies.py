import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.location import LocationSource
from app.models.user import User
from app.providers.location import get_location_provider
from app.providers.location.base import LocationCandidate
from app.schemas.company import CompanyCreate, CompanyListItem, CompanyOut, CompanyUpdate, Page
from app.schemas.location import LocationCandidatesOut, LocationResolveRequest
from app.services.activity_service import ActivityService
from app.services.company_service import CompanyService
from app.services.location_service import LocationService

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=Page)
def list_companies(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page:
    service = CompanyService(db)
    items, total = service.list_companies(search=search, page=page, page_size=page_size)
    return Page(
        items=[CompanyListItem.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyOut:
    service = CompanyService(db)
    company = service.create_company(payload)
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="company",
        entity_id=company.id,
        action="created",
    )
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyOut:
    service = CompanyService(db)
    company = service.get_company(company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return CompanyOut.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyOut:
    service = CompanyService(db)
    company = service.get_company(company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    company = service.update_company(company, payload)
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="company",
        entity_id=company.id,
        action="edited",
        metadata=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    service = CompanyService(db)
    company = service.get_company(company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="company",
        entity_id=company.id,
        action="deleted",
        metadata={"name": company.name},
    )
    service.delete_company(company)
    db.commit()


@router.get("/{company_id}/location/candidates", response_model=LocationCandidatesOut)
def get_location_candidates(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationCandidatesOut:
    service = CompanyService(db)
    company = service.get_company(company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    location = next((loc for loc in company.locations if loc.is_primary), None)
    raw_address = location.address_line_1 if location else None
    city = location.city if location else None
    state = location.state if location else None
    if not (raw_address or city or state):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This company has no address on file to search for"
        )

    location_service = LocationService(db, get_location_provider())
    candidates = location_service.search_candidates(
        company_name=company.name,
        raw_address=raw_address,
        city=city,
        state=state,
    )
    return LocationCandidatesOut(candidates=candidates)


@router.post("/{company_id}/location/resolve", response_model=CompanyOut)
def resolve_location(
    company_id: uuid.UUID,
    payload: LocationResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyOut:
    service = CompanyService(db)
    company = service.get_company(company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    location_service = LocationService(db, get_location_provider())
    candidate = LocationCandidate(**payload.candidate.model_dump())
    location_service.apply_candidate(
        company_id=company.id,
        candidate=candidate,
        search_query=company.name,
        source=LocationSource.VERIFIED_BUSINESS,
    )
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="company",
        entity_id=company.id,
        action="location_resolved",
        metadata={"address": candidate.formatted_address},
    )
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)
