import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.company import Company
from app.models.contact import Contact
from app.models.location import Location
from app.models.meeting import Meeting, MeetingStatus
from app.models.user import User
from app.schemas.meeting import MeetingCreate, MeetingUpdate


def _add_minutes(t, minutes: int):
    dt = datetime.combine(datetime.today(), t) + timedelta(minutes=minutes)
    return dt.time()


class MeetingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_conflicts(
        self, salesperson_id: uuid.UUID, date, start_time, end_time, *, exclude_meeting_id=None
    ) -> list[Meeting]:
        query = self.db.query(Meeting).filter(
            Meeting.salesperson_id == salesperson_id,
            Meeting.date == date,
            Meeting.status.notin_([MeetingStatus.CANCELLED, MeetingStatus.NO_SHOW]),
            Meeting.start_time < end_time,
            Meeting.end_time > start_time,
        )
        if exclude_meeting_id:
            query = query.filter(Meeting.id != exclude_meeting_id)
        return query.all()

    def create_meeting(
        self, payload: MeetingCreate, *, created_by_id: uuid.UUID, is_planner_generated: bool = False
    ) -> Meeting:
        end_time = _add_minutes(payload.start_time, payload.duration_minutes)
        location = (
            self.db.query(Location)
            .filter(Location.company_id == payload.company_id, Location.is_primary.is_(True))
            .first()
        )
        meeting = Meeting(
            company_id=payload.company_id,
            contact_id=payload.contact_id,
            salesperson_id=payload.salesperson_id,
            location_id=location.id if location else None,
            date=payload.date,
            start_time=payload.start_time,
            end_time=end_time,
            duration_minutes=payload.duration_minutes,
            notes=payload.notes,
            created_by_id=created_by_id,
            is_planner_generated=is_planner_generated,
        )
        self.db.add(meeting)
        self.db.flush()
        return meeting

    def update_meeting(self, meeting: Meeting, payload: MeetingUpdate) -> Meeting:
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(meeting, field, value)
        if "start_time" in data or "duration_minutes" in data:
            meeting.end_time = _add_minutes(meeting.start_time, meeting.duration_minutes)
        self.db.flush()
        return meeting

    def get_detail_row(self, meeting_id: uuid.UUID):
        return (
            self.db.query(Meeting)
            .options(
                joinedload(Meeting.company),
                joinedload(Meeting.contact),
                joinedload(Meeting.salesperson),
                joinedload(Meeting.location),
            )
            .filter(Meeting.id == meeting_id)
            .first()
        )

    def list_meetings(
        self,
        *,
        salesperson_id: uuid.UUID | None = None,
        date_from=None,
        date_to=None,
        status: MeetingStatus | None = None,
    ) -> list[Meeting]:
        query = self.db.query(Meeting).options(
            joinedload(Meeting.company), joinedload(Meeting.contact), joinedload(Meeting.salesperson)
        )
        if salesperson_id:
            query = query.filter(Meeting.salesperson_id == salesperson_id)
        if date_from:
            query = query.filter(Meeting.date >= date_from)
        if date_to:
            query = query.filter(Meeting.date <= date_to)
        if status:
            query = query.filter(Meeting.status == status)
        return query.order_by(Meeting.date, Meeting.start_time).all()


def to_meeting_detail(meeting: Meeting) -> dict:
    return {
        "id": meeting.id,
        "company_id": meeting.company_id,
        "contact_id": meeting.contact_id,
        "salesperson_id": meeting.salesperson_id,
        "location_id": meeting.location_id,
        "date": meeting.date,
        "start_time": meeting.start_time,
        "end_time": meeting.end_time,
        "duration_minutes": meeting.duration_minutes,
        "status": meeting.status,
        "notes": meeting.notes,
        "next_follow_up_date": meeting.next_follow_up_date,
        "company_name": meeting.company.name,
        "contact_name": meeting.contact.full_name if meeting.contact else None,
        "salesperson_name": meeting.salesperson.name,
        "address_line_1": meeting.location.address_line_1 if meeting.location else None,
        "city": meeting.location.city if meeting.location else None,
        "state": meeting.location.state if meeting.location else None,
        "latitude": meeting.location.latitude if meeting.location else None,
        "longitude": meeting.location.longitude if meeting.location else None,
        "company_phone": meeting.company.phone,
        "company_website": meeting.company.website,
    }
