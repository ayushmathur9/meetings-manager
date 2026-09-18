import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactOut, ContactUpdate
from app.services.activity_service import ActivityService

router = APIRouter(tags=["contacts"])


@router.get("/companies/{company_id}/contacts", response_model=list[ContactOut])
def list_contacts(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ContactOut]:
    contacts = db.query(Contact).filter(Contact.company_id == company_id).all()
    return [ContactOut.model_validate(c) for c in contacts]


@router.post("/companies/{company_id}/contacts", response_model=ContactOut, status_code=201)
def create_contact(
    company_id: uuid.UUID,
    payload: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactOut:
    contact = Contact(company_id=company_id, source="manual", **payload.model_dump())
    db.add(contact)
    ActivityService(db).log(
        user_id=current_user.id, entity_type="contact", entity_id=contact.id, action="created"
    )
    db.commit()
    db.refresh(contact)
    return ContactOut.model_validate(contact)


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactOut:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return ContactOut.model_validate(contact)
