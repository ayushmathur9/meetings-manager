import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.company import CompanyStatus
from app.models.location import VerificationStatus


class ProspectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prospect_id: uuid.UUID | None
    company_id: uuid.UUID
    company_name: str
    industry: str | None
    phone: str | None
    status: CompanyStatus
    employee_count: int | None
    assigned_user_id: uuid.UUID | None
    assigned_user_name: str | None
    address_line_1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    latitude: float | None
    longitude: float | None
    verification_status: VerificationStatus | None
    distance_meters: float | None = None
    has_contact: bool
    contact_count: int
    next_meeting_date: datetime | None = None


class ProspectFilters(BaseModel):
    search: str | None = None
    industry: str | None = None
    status: CompanyStatus | None = None
    assigned_user_id: uuid.UUID | None = None
    unassigned_only: bool = False
    min_employees: int | None = None
    max_employees: int | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    verification_status: VerificationStatus | None = None
    missing_phone: bool = False
    missing_website: bool = False
    missing_contact: bool = False
    center_lat: float | None = None
    center_lng: float | None = None
    radius_miles: float | None = None
    page: int = 1
    page_size: int = 50


class BulkAssignRequest(BaseModel):
    company_ids: list[uuid.UUID]
    assigned_user_id: uuid.UUID


class BulkStatusRequest(BaseModel):
    company_ids: list[uuid.UUID]
    status: CompanyStatus


class ProspectPage(BaseModel):
    items: list[ProspectListItem]
    total: int
    page: int
    page_size: int
