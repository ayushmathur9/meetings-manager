import uuid

from pydantic import BaseModel, ConfigDict

from app.models.contact import ContactType, ContactVerificationStatus


class ContactBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    contact_type: ContactType = ContactType.UNKNOWN


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    contact_type: ContactType | None = None


class ContactOut(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    verification_status: ContactVerificationStatus
    source: str | None
