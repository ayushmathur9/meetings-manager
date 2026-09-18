import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.company import CompanyStatus
from app.models.location import VerificationStatus
from app.models.user import User, UserRole
from app.schemas.prospect import (
    BulkAssignRequest,
    BulkStatusRequest,
    ProspectFilters,
    ProspectListItem,
    ProspectPage,
)
from app.services.activity_service import ActivityService
from app.services.prospect_service import ProspectService

router = APIRouter(prefix="/prospects", tags=["prospects"])


@router.get("", response_model=ProspectPage)
def list_prospects(
    search: str | None = None,
    industry: str | None = None,
    status: CompanyStatus | None = None,
    assigned_user_id: uuid.UUID | None = None,
    unassigned_only: bool = False,
    min_employees: int | None = None,
    max_employees: int | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    verification_status: VerificationStatus | None = None,
    missing_phone: bool = False,
    missing_website: bool = False,
    missing_contact: bool = False,
    center_lat: float | None = None,
    center_lng: float | None = None,
    radius_miles: float | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProspectPage:
    filters = ProspectFilters(
        search=search,
        industry=industry,
        status=status,
        assigned_user_id=assigned_user_id,
        unassigned_only=unassigned_only,
        min_employees=min_employees,
        max_employees=max_employees,
        city=city,
        state=state,
        postal_code=postal_code,
        verification_status=verification_status,
        missing_phone=missing_phone,
        missing_website=missing_website,
        missing_contact=missing_contact,
        center_lat=center_lat,
        center_lng=center_lng,
        radius_miles=radius_miles,
        page=page,
        page_size=page_size,
    )
    restrict_to_user = current_user.id if current_user.role == UserRole.SALESPERSON else None
    service = ProspectService(db)
    items, total = service.list_prospects(filters, restrict_to_user=restrict_to_user)
    return ProspectPage(
        items=[ProspectListItem(**item) for item in items], total=total, page=page, page_size=page_size
    )


@router.post("/bulk-assign", response_model=list[uuid.UUID])
def bulk_assign(
    payload: BulkAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[uuid.UUID]:
    service = ProspectService(db)
    prospects = service.bulk_assign(payload, assigned_by_id=current_user.id)
    activity_service = ActivityService(db)
    for prospect in prospects:
        activity_service.log(
            user_id=current_user.id,
            entity_type="prospect",
            entity_id=prospect.company_id,
            action="assigned",
            metadata={"assigned_user_id": str(payload.assigned_user_id)},
        )
    db.commit()
    return [p.company_id for p in prospects]


@router.post("/bulk-status")
def bulk_status(
    payload: BulkStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    service = ProspectService(db)
    service.bulk_status(payload)
    activity_service = ActivityService(db)
    for company_id in payload.company_ids:
        activity_service.log(
            user_id=current_user.id,
            entity_type="company",
            entity_id=company_id,
            action="status_changed",
            metadata={"status": payload.status.value},
        )
    db.commit()
    return {"detail": "Status updated"}


@router.patch("/{company_id}/assign")
def assign_single(
    company_id: uuid.UUID,
    assigned_user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    service = ProspectService(db)
    service.assign_single(company_id, assigned_user_id, assigned_by_id=current_user.id)
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="prospect",
        entity_id=company_id,
        action="assigned" if assigned_user_id else "unassigned",
        metadata={"assigned_user_id": str(assigned_user_id) if assigned_user_id else None},
    )
    db.commit()
    return {"detail": "Assignment updated"}
