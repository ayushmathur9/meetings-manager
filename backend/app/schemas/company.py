import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.company import CompanyStatus
from app.schemas.contact import ContactOut
from app.schemas.location import LocationOut


class CompanyBase(BaseModel):
    name: str
    legal_name: str | None = None
    industry: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    employee_count: int | None = None
    location_count: int | None = None
    parent_company: str | None = None
    notes: str | None = None
    status: CompanyStatus = CompanyStatus.NEW


class CompanyCreate(CompanyBase):
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


ADDRESS_FIELDS = ("address_line_1", "city", "state", "postal_code", "country")


class CompanyUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    industry: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    employee_count: int | None = None
    location_count: int | None = None
    parent_company: str | None = None
    notes: str | None = None
    status: CompanyStatus | None = None
    # Changing any of these replaces the primary location and re-verifies it.
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class CompanyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    phone: str | None
    status: CompanyStatus
    is_demo: bool
    created_at: datetime


class CompanyOut(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    bigin_account_id: str | None = None
    crm_owner_name: str | None = None
    crm_status: str | None = None
    crm_synced_at: datetime | None = None
    crm_deleted_at: datetime | None = None
    locations: list[LocationOut] = []
    contacts: list[ContactOut] = []


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
