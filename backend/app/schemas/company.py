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
    locations: list[LocationOut] = []
    contacts: list[ContactOut] = []


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
