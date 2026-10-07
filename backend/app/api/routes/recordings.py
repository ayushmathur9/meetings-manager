"""Meeting recordings + transcripts.

Access: admins, or the salesperson the meeting is assigned to. Other users
get 404 (not 403) so recording ids can't be probed. Audio is never public:
S3 audio is a short-lived presigned redirect, local audio is streamed by
this API.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.meeting import Meeting
from app.models.recording import MeetingRecording, RecordingStatus
from app.models.user import User
from app.services import background
from app.services.activity_service import ActivityService
from app.services.recording_service import (
    RecordingError,
    RecordingService,
    can_access_meeting,
    can_delete_recording,
    process_recording_job,
)
from app.services.storage import StorageError

router = APIRouter(tags=["recordings"])


class TranscriptSegmentOut(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    language: str | None
    text: str
    segments: list[TranscriptSegmentOut] | None
    speaker_count: int | None
    duration_seconds: float | None
    created_at: datetime


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID
    status: RecordingStatus
    content_type: str | None
    size_bytes: int | None
    duration_seconds: float | None
    provider: str | None
    error: str | None
    created_at: datetime
    uploaded_at: datetime | None
    completed_at: datetime | None
    created_by_name: str | None = None
    can_delete: bool = False
    transcript: TranscriptOut | None = None


class TranscriptionConfigOut(BaseModel):
    enabled: bool
    provider: str | None
    max_upload_mb: int


def _out(recording: MeetingRecording, user: User) -> RecordingOut:
    out = RecordingOut.model_validate(recording)
    out.created_by_name = recording.created_by.name if recording.created_by else None
    out.can_delete = can_delete_recording(user, recording)
    return out


def _meeting(db: Session, meeting_id: uuid.UUID, user: User) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None or not can_access_meeting(user, meeting):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
    return meeting


def _recording(db: Session, recording_id: uuid.UUID, user: User) -> MeetingRecording:
    recording = (
        db.query(MeetingRecording)
        .options(selectinload(MeetingRecording.meeting), selectinload(MeetingRecording.transcript))
        .filter(MeetingRecording.id == recording_id)
        .first()
    )
    if recording is None or not can_access_meeting(user, recording.meeting):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    return recording


@router.get("/recordings/config", response_model=TranscriptionConfigOut)
def transcription_config(current_user: User = Depends(get_current_user)) -> TranscriptionConfigOut:
    from app.services.transcription import get_transcription_provider

    provider = get_transcription_provider()
    return TranscriptionConfigOut(
        enabled=bool(provider and provider.is_configured),
        provider=provider.name if provider else None,
        max_upload_mb=get_settings().recording_max_upload_mb,
    )


@router.get("/meetings/{meeting_id}/recordings", response_model=list[RecordingOut])
def list_recordings(
    meeting_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[RecordingOut]:
    _meeting(db, meeting_id, current_user)
    rows = (
        db.query(MeetingRecording)
        .options(selectinload(MeetingRecording.transcript), selectinload(MeetingRecording.meeting))
        .filter(MeetingRecording.meeting_id == meeting_id)
        .order_by(MeetingRecording.created_at.desc())
        .all()
    )
    return [_out(r, current_user) for r in rows]


@router.post("/meetings/{meeting_id}/recordings", response_model=RecordingOut, status_code=status.HTTP_201_CREATED)
def upload_recording(
    meeting_id: uuid.UUID,
    file: UploadFile = File(...),
    duration_seconds: float | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecordingOut:
    meeting = _meeting(db, meeting_id, current_user)
    max_bytes = get_settings().recording_max_upload_mb * 1024 * 1024
    size = file.size
    if size is None:  # not reported by the parser — measure the spooled file
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    if size > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Recording is larger than the upload limit.")
    try:
        recording = RecordingService(db).create(
            meeting=meeting,
            user=current_user,
            fileobj=file.file,
            content_type=file.content_type,
            size_bytes=size,
            duration_seconds=duration_seconds,
        )
    except RecordingError as exc:
        db.commit()  # keep the FAILED row for a storage failure
        raise HTTPException(exc.status_code, exc.message)
    ActivityService(db).log(
        user_id=current_user.id, entity_type="meeting", entity_id=meeting.id, action="recording_uploaded",
        metadata={"recording_id": str(recording.id)},
    )
    db.commit()
    db.refresh(recording)
    background.submit(process_recording_job, recording.id)
    return _out(recording, current_user)


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
def get_recording(
    recording_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> RecordingOut:
    return _out(_recording(db, recording_id, current_user), current_user)


@router.get("/recordings/{recording_id}/audio")
def get_audio(recording_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    recording = _recording(db, recording_id, current_user)
    if not recording.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audio not available")
    service = RecordingService(db)
    url = service.storage.presigned_url(recording.storage_key)
    if url:
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    path = service.storage.local_path(recording.storage_key)
    if path is not None and path.exists():
        return FileResponse(path, media_type=recording.content_type or "audio/webm")
    try:
        stream = service.storage.open(recording.storage_key)
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audio not available")
    return StreamingResponse(stream, media_type=recording.content_type or "audio/webm")


def _timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@router.get("/recordings/{recording_id}/transcript.txt", response_class=PlainTextResponse)
def download_transcript(
    recording_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PlainTextResponse:
    recording = _recording(db, recording_id, current_user)
    transcript = recording.transcript
    if transcript is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcript not ready")
    meeting = recording.meeting
    header = [
        f"Meeting transcript — {meeting.company.name}",
        f"Date: {meeting.date.isoformat()} {meeting.start_time.strftime('%H:%M')}",
    ]
    if transcript.duration_seconds:
        header.append(f"Duration: {_timestamp(transcript.duration_seconds)}")
    if transcript.speaker_count:
        header.append(f"Speakers detected: {transcript.speaker_count}")
    body = "\n\n".join(
        f"[{_timestamp(s['start'])}] Speaker {s['speaker']}:\n{s['text']}" for s in transcript.segments or []
    ) or transcript.text
    filename = f"transcript-{meeting.date.isoformat()}-{recording.id.hex[:8]}.txt"
    return PlainTextResponse(
        "\n".join(header) + "\n\n" + body + "\n",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/recordings/{recording_id}/retry", response_model=RecordingOut, status_code=status.HTTP_202_ACCEPTED)
def retry_transcription(
    recording_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> RecordingOut:
    recording = _recording(db, recording_id, current_user)
    if recording.status != RecordingStatus.FAILED or not recording.storage_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a failed recording with saved audio can be retried")
    recording.status = RecordingStatus.PROCESSING
    recording.error = None
    recording.submitted_at = None
    recording.provider_job_id = None
    recording.attempts = 0
    db.commit()
    db.refresh(recording)
    background.submit(process_recording_job, recording.id)
    return _out(recording, current_user)


@router.delete("/recordings/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(
    recording_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    recording = _recording(db, recording_id, current_user)
    if not can_delete_recording(current_user, recording):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't delete this recording")
    meeting_id = recording.meeting_id
    try:
        RecordingService(db).delete(recording)
    except RecordingError as exc:
        raise HTTPException(exc.status_code, exc.message)
    ActivityService(db).log(
        user_id=current_user.id, entity_type="meeting", entity_id=meeting_id, action="recording_deleted",
        metadata={"recording_id": str(recording_id)},
    )
    db.commit()
