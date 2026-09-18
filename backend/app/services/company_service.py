import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models.company import Company
from app.models.location import Location
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.normalization import extract_domain, normalize_company_name, normalize_phone


class CompanyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_companies(
        self, *, search: str | None = None, page: int = 1, page_size: int = 50
    ) -> tuple[list[Company], int]:
        query = self.db.query(Company)
        if search:
            like = f"%{search.lower()}%"
            query = query.filter(
                or_(Company.name.ilike(like), Company.industry.ilike(like), Company.phone.ilike(like))
            )
        total = query.count()
        items = (
            query.order_by(Company.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_company(self, company_id: uuid.UUID) -> Company | None:
        return (
            self.db.query(Company)
            .options(selectinload(Company.locations), selectinload(Company.contacts))
            .filter(Company.id == company_id)
            .first()
        )

    def create_company(self, payload: CompanyCreate) -> Company:
        company = Company(
            name=payload.name,
            legal_name=payload.legal_name,
            normalized_name=normalize_company_name(payload.name),
            industry=payload.industry,
            website=payload.website,
            domain=extract_domain(payload.website),
            phone=payload.phone,
            phone_normalized=normalize_phone(payload.phone),
            email=payload.email,
            employee_count=payload.employee_count,
            location_count=payload.location_count,
            parent_company=payload.parent_company,
            notes=payload.notes,
            status=payload.status,
        )
        self.db.add(company)
        self.db.flush()

        if payload.address_line_1 or payload.city or payload.state:
            location = Location(
                company_id=company.id,
                is_primary=True,
                address_line_1=payload.address_line_1,
                city=payload.city,
                state=payload.state,
                postal_code=payload.postal_code,
                country=payload.country or "USA",
            )
            self.db.add(location)
            self.db.flush()

        return company

    def update_company(self, company: Company, payload: CompanyUpdate) -> Company:
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(company, field, value)
        if "name" in data:
            company.normalized_name = normalize_company_name(company.name)
        if "website" in data:
            company.domain = extract_domain(company.website)
        if "phone" in data:
            company.phone_normalized = normalize_phone(company.phone)
        self.db.flush()
        return company

    def delete_company(self, company: Company) -> None:
        self.db.delete(company)
        self.db.flush()
