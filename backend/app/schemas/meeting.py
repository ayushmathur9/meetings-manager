import uuid
import datetime as dt

from pydantic import BaseModel, ConfigDict

from app.models.meeting import DEFAULT_MEETING_DURATION_MINUTES, MeetingStatus


class MeetingCreate(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    salesperson_id: uuid.UUID
    date: dt.date
    start_time: dt.time
    duration_minutes: int = DEFAULT_MEETING_DURATION_MINUTES
    notes: str | None = None


class MeetingUpdate(BaseModel):
    contact_id: uuid.UUID | None = None
    date: dt.date | None = None
    start_time: dt.time | None = None
    duration_minutes: int | None = None
    status: MeetingStatus | None = None
    notes: str | None = None
    next_follow_up_date: dt.date | None = None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    contact_id: uuid.UUID | None
    salesperson_id: uuid.UUID
    location_id: uuid.UUID | None
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    duration_minutes: int
    status: MeetingStatus
    notes: str | None
    next_follow_up_date: dt.date | None


class MeetingDetail(MeetingOut):
    company_name: str
    contact_name: str | None = None
    salesperson_name: str
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    company_phone: str | None = None
    company_website: str | None = None


class ConflictWarning(BaseModel):
    conflicting_meeting_id: uuid.UUID
    company_name: str
    start_time: dt.time
    end_time: dt.time
