import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.meeting import Meeting, MeetingStatus
from app.models.user import User, UserRole
from app.schemas.meeting import ConflictWarning, MeetingCreate, MeetingDetail, MeetingOut, MeetingUpdate
from app.services.activity_service import ActivityService
from app.services.meeting_service import MeetingService, to_meeting_detail

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("", response_model=list[MeetingDetail])
def list_meetings(
    salesperson_id: uuid.UUID | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    status_filter: MeetingStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MeetingDetail]:
    effective_salesperson_id = salesperson_id
    if current_user.role == UserRole.SALESPERSON:
        effective_salesperson_id = current_user.id

    service = MeetingService(db)
    meetings = service.list_meetings(
        salesperson_id=effective_salesperson_id,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
    )
    return [MeetingDetail(**to_meeting_detail(m)) for m in meetings]


@router.get("/conflicts", response_model=list[ConflictWarning])
def check_conflicts(
    salesperson_id: uuid.UUID,
    date: date_type,
    start_time: str,
    duration_minutes: int = 25,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ConflictWarning]:
    from datetime import datetime, timedelta

    start = datetime.strptime(start_time, "%H:%M").time()
    end_dt = datetime.combine(date, start) + timedelta(minutes=duration_minutes)
    service = MeetingService(db)
    conflicts = service.find_conflicts(salesperson_id, date, start, end_dt.time())
    return [
        ConflictWarning(
            conflicting_meeting_id=c.id,
            company_name=c.company.name,
            start_time=c.start_time,
            end_time=c.end_time,
        )
        for c in conflicts
    ]


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(
    payload: MeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingOut:
    service = MeetingService(db)
    meeting = service.create_meeting(payload, created_by_id=current_user.id)
    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="meeting",
        entity_id=meeting.id,
        action="scheduled",
        metadata={"company_id": str(meeting.company_id)},
    )
    db.commit()
    db.refresh(meeting)
    return MeetingOut.model_validate(meeting)


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingDetail:
    service = MeetingService(db)
    meeting = service.get_detail_row(meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
    return MeetingDetail(**to_meeting_detail(meeting))


@router.patch("/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: uuid.UUID,
    payload: MeetingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingOut:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
    service = MeetingService(db)
    meeting = service.update_meeting(meeting, payload)

    action = "edited"
    if payload.status == MeetingStatus.COMPLETED:
        action = "completed"
    elif payload.status == MeetingStatus.CANCELLED:
        action = "cancelled"
    elif payload.status == MeetingStatus.IN_PROGRESS:
        action = "started"

    ActivityService(db).log(
        user_id=current_user.id,
        entity_type="meeting",
        entity_id=meeting.id,
        action=action,
        metadata=payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(meeting)
    return MeetingOut.model_validate(meeting)
