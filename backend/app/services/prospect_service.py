import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.models.company import Company
from app.models.contact import Contact
from app.models.location import Location, VerificationStatus
from app.models.meeting import Meeting, MeetingStatus
from app.models.prospect import Prospect
from app.models.user import User
from app.schemas.prospect import BulkAssignRequest, BulkStatusRequest, ProspectFilters

_METERS_PER_MILE = 1609.344


class ProspectService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _base_query(self, filters: ProspectFilters, *, restrict_to_user: uuid.UUID | None = None):
        assigned_user = aliased(User)
        contact_count = (
            self.db.query(func.count(Contact.id))
            .filter(Contact.company_id == Company.id)
            .correlate(Company)
            .scalar_subquery()
        )
        next_meeting = (
            self.db.query(func.min(Meeting.date))
            .filter(
                Meeting.company_id == Company.id,
                Meeting.status.in_([MeetingStatus.SCHEDULED, MeetingStatus.CONFIRMED]),
            )
            .correlate(Company)
            .scalar_subquery()
        )

        query = (
            self.db.query(
                Prospect.id.label("prospect_id"),
                Company.id.label("company_id"),
                Company.name.label("company_name"),
                Company.industry,
                Company.phone,
                Company.status,
                Company.employee_count,
                Company.website,
                Prospect.assigned_user_id,
                assigned_user.name.label("assigned_user_name"),
                Location.address_line_1,
                Location.city,
                Location.state,
                Location.postal_code,
                Location.latitude,
                Location.longitude,
                Location.verification_status,
                contact_count.label("contact_count"),
                next_meeting.label("next_meeting_date"),
            )
            .select_from(Company)
            .outerjoin(Prospect, Prospect.company_id == Company.id)
            .outerjoin(assigned_user, assigned_user.id == Prospect.assigned_user_id)
            .outerjoin(Location, (Location.company_id == Company.id) & Location.is_primary.is_(True))
        )

        if restrict_to_user is not None:
            query = query.filter(Prospect.assigned_user_id == restrict_to_user)

        if filters.search:
            like = f"%{filters.search.lower()}%"
            query = query.filter(
                or_(Company.name.ilike(like), Company.industry.ilike(like), Company.phone.ilike(like))
            )
        if filters.industry:
            query = query.filter(Company.industry.ilike(f"%{filters.industry}%"))
        if filters.status:
            query = query.filter(Company.status == filters.status)
        if filters.assigned_user_id:
            query = query.filter(Prospect.assigned_user_id == filters.assigned_user_id)
        if filters.unassigned_only:
            query = query.filter(Prospect.assigned_user_id.is_(None))
        if filters.min_employees is not None:
            query = query.filter(Company.employee_count >= filters.min_employees)
        if filters.max_employees is not None:
            query = query.filter(Company.employee_count <= filters.max_employees)
        if filters.city:
            query = query.filter(Location.city.ilike(f"%{filters.city}%"))
        if filters.state:
            query = query.filter(Location.state.ilike(f"%{filters.state}%"))
        if filters.postal_code:
            query = query.filter(Location.postal_code == filters.postal_code)
        if filters.verification_status:
            query = query.filter(Location.verification_status == filters.verification_status)
        if filters.missing_phone:
            query = query.filter(or_(Company.phone.is_(None), Company.phone == ""))
        if filters.missing_website:
            query = query.filter(or_(Company.website.is_(None), Company.website == ""))
        if filters.missing_contact:
            query = query.filter(contact_count == 0)

        if filters.center_lat is not None and filters.center_lng is not None and filters.radius_miles:
            # Bounding-box prefilter (fast, index-friendly) + exact haversine distance.
            radius_meters = filters.radius_miles * _METERS_PER_MILE
            lat_delta = filters.radius_miles / 69.0
            lng_delta = filters.radius_miles / 54.6
            query = query.filter(
                Location.latitude.between(filters.center_lat - lat_delta, filters.center_lat + lat_delta),
                Location.longitude.between(
                    filters.center_lng - lng_delta, filters.center_lng + lng_delta
                ),
            )

        return query

    def list_prospects(
        self, filters: ProspectFilters, *, restrict_to_user: uuid.UUID | None = None
    ) -> tuple[list[dict], int]:
        query = self._base_query(filters, restrict_to_user=restrict_to_user)
        all_rows = query.all()

        results = []
        for row in all_rows:
            data = dict(row._mapping)
            distance_meters = None
            if (
                filters.center_lat is not None
                and filters.center_lng is not None
                and data["latitude"] is not None
                and data["longitude"] is not None
            ):
                distance_meters = self._haversine_meters(
                    filters.center_lat, filters.center_lng, data["latitude"], data["longitude"]
                )
                if filters.radius_miles and distance_meters > filters.radius_miles * _METERS_PER_MILE:
                    continue
            data["distance_meters"] = distance_meters
            data["has_contact"] = data["contact_count"] > 0
            results.append(data)

        if filters.center_lat is not None and filters.center_lng is not None:
            results.sort(key=lambda r: (r["distance_meters"] is None, r["distance_meters"] or 0))

        total = len(results)
        start = (filters.page - 1) * filters.page_size
        end = start + filters.page_size
        return results[start:end], total

    @staticmethod
    def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        from math import asin, cos, radians, sin, sqrt

        r = 6371000
        phi1, phi2 = radians(lat1), radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lng2 - lng1)
        a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
        return 2 * r * asin(sqrt(a))

    def get_or_create_prospect(self, company_id: uuid.UUID) -> Prospect:
        prospect = self.db.query(Prospect).filter(Prospect.company_id == company_id).first()
        if prospect is None:
            prospect = Prospect(company_id=company_id)
            self.db.add(prospect)
            self.db.flush()
        return prospect

    def bulk_assign(self, payload: BulkAssignRequest, *, assigned_by_id: uuid.UUID) -> list[Prospect]:
        prospects = []
        for company_id in payload.company_ids:
            prospect = self.get_or_create_prospect(company_id)
            prospect.assigned_user_id = payload.assigned_user_id
            prospect.assigned_at = datetime.now(timezone.utc)
            prospect.assigned_by_id = assigned_by_id
            prospects.append(prospect)
        self.db.flush()
        return prospects

    def bulk_status(self, payload: BulkStatusRequest) -> None:
        self.db.query(Company).filter(Company.id.in_(payload.company_ids)).update(
            {Company.status: payload.status}, synchronize_session=False
        )
        self.db.flush()

    def assign_single(
        self, company_id: uuid.UUID, assigned_user_id: uuid.UUID | None, *, assigned_by_id: uuid.UUID
    ) -> Prospect:
        prospect = self.get_or_create_prospect(company_id)
        prospect.assigned_user_id = assigned_user_id
        prospect.assigned_at = datetime.now(timezone.utc) if assigned_user_id else None
        prospect.assigned_by_id = assigned_by_id if assigned_user_id else None
        self.db.flush()
        return prospect
