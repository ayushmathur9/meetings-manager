import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models.company import Company
from app.models.location import Location, LocationSource
from app.providers.location import get_geocoding_provider
from app.providers.location.base import LocationProvider
from app.schemas.company import ADDRESS_FIELDS, CompanyCreate, CompanyUpdate
from app.services.location_service import LocationService
from app.services.normalization import extract_domain, normalize_company_name, normalize_phone


class CompanyService:
    def __init__(self, db: Session, location_provider: LocationProvider | None = None) -> None:
        self.db = db
        self._location_provider = location_provider

    def _location_service(self) -> LocationService:
        if self._location_provider is None:
            self._location_provider = get_geocoding_provider()
        return LocationService(self.db, self._location_provider)

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
                source=LocationSource.USER_PROVIDED,
            )
            self.db.add(location)
            self.db.flush()
            # Look the address up right away so the company is routable as
            # soon as it's saved; anything not confidently matched is flagged
            # for review (or retried by the background sweep).
            self._location_service().verify_or_flag(
                company_id=company.id,
                company_name=company.name,
                raw_address=payload.address_line_1,
                city=payload.city,
                state=payload.state,
                postal_code=payload.postal_code,
                country=payload.country,
            )

        return company

    def update_company(self, company: Company, payload: CompanyUpdate) -> Company:
        data = payload.model_dump(exclude_unset=True)
        address = {field: data.pop(field) for field in ADDRESS_FIELDS if field in data}
        for field, value in data.items():
            setattr(company, field, value)
        if "name" in data:
            company.normalized_name = normalize_company_name(company.name)
        if "website" in data:
            company.domain = extract_domain(company.website)
        if "phone" in data:
            company.phone_normalized = normalize_phone(company.phone)
        self.db.flush()
        if address:
            self._update_address(company, address)
        return company

    def _update_address(self, company: Company, changes: dict) -> None:
        """Apply an address edit; only an actual change re-verifies (and
        replaces an existing verified location)."""
        primary = next((loc for loc in company.locations if loc.is_primary), None)
        current = {
            "address_line_1": primary.address_line_1 if primary else None,
            "city": primary.city if primary else None,
            "state": primary.state if primary else None,
            "postal_code": primary.postal_code if primary else None,
            "country": primary.country if primary else None,
        }
        cleaned = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in changes.items()}
        updated = {**current, **cleaned}
        if updated == current:
            return
        self._location_service().replace_address(company_id=company.id, company_name=company.name, **updated)

    def delete_company(self, company: Company) -> None:
        self.db.delete(company)
        self.db.flush()
