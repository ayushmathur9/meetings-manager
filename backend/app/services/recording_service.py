"""Meeting recordings: storage, transcription jobs, permissions.

Lifecycle (status on MeetingRecording):
  browser records -> upload -> stored in object storage -> PROCESSING
  -> provider job submitted (job id stored) -> poller sees completion
  -> MeetingTranscript written -> COMPLETED   (or FAILED with a reason)

Everything needed to resume lives on the row, so a restart mid-way is
picked up by ``poll_pending_recordings`` (the periodic poller).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.models.meeting import Meeting
from app.models.recording import MeetingRecording, MeetingTranscript, RecordingStatus
from app.models.user import User, UserRole
from app.services.storage import ObjectStorage, StorageError, get_storage
from app.services.transcription import (
    AudioSource,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptResult,
    get_transcription_provider,
)

logger = logging.getLogger("app.transcription")

ALLOWED_CONTENT_TYPES = {
    "audio/webm": "webm",
    "video/webm": "webm",  # some browsers label audio-only WebM this way
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}
MAX_ATTEMPTS = 3
STUCK_AFTER = timedelta(minutes=30)
UPLOAD_ABANDONED_AFTER = timedelta(hours=1)


class RecordingError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------ permissions
def can_access_meeting(user: User, meeting: Meeting) -> bool:
    """Admins: every meeting. Salespeople: only meetings they are assigned to."""
    return user.role == UserRole.ADMIN or meeting.salesperson_id == user.id


def can_delete_recording(user: User, recording: MeetingRecording) -> bool:
    return user.role == UserRole.ADMIN or recording.created_by_id == user.id or (
        recording.meeting is not None and recording.meeting.salesperson_id == user.id
    )


def normalize_content_type(content_type: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    if base not in ALLOWED_CONTENT_TYPES:
        raise RecordingError(f"Unsupported audio format ({base or 'unknown'}).", 415)
    return "audio/webm" if base == "video/webm" else base


class RecordingService:
    def __init__(
        self,
        db: Session,
        storage: ObjectStorage | None = None,
        provider: TranscriptionProvider | None = None,
    ) -> None:
        self.db = db
        self._storage = storage
        self._provider = provider
        self._provider_loaded = provider is not None

    @property
    def storage(self) -> ObjectStorage:
        if self._storage is None:
            self._storage = get_storage()
        return self._storage

    @property
    def provider(self) -> TranscriptionProvider | None:
        if not self._provider_loaded:
            self._provider = get_transcription_provider()
            self._provider_loaded = True
        return self._provider

    # ---------------------------------------------------------------- create
    def create(
        self,
        *,
        meeting: Meeting,
        user: User,
        fileobj: BinaryIO,
        content_type: str | None,
        size_bytes: int | None,
        duration_seconds: float | None,
    ) -> MeetingRecording:
        ctype = normalize_content_type(content_type)
        if not size_bytes:
            raise RecordingError("The recording is empty.")
        recording_id = uuid.uuid4()
        key = f"recordings/{meeting.id}/{recording_id}.{ALLOWED_CONTENT_TYPES[ctype]}"
        recording = MeetingRecording(
            id=recording_id,
            meeting_id=meeting.id,
            created_by_id=user.id,
            status=RecordingStatus.UPLOADING,
            content_type=ctype,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds if duration_seconds and duration_seconds > 0 else None,
        )
        self.db.add(recording)
        self.db.flush()
        try:
            self.storage.put(key, fileobj, ctype)
        except StorageError as exc:
            recording.status = RecordingStatus.FAILED
            recording.error = str(exc)
            self.db.flush()
            raise RecordingError("The recording could not be saved to storage. Please try again.", 502) from exc
        recording.storage_backend = self.storage.name
        recording.storage_key = key
        recording.uploaded_at = _now()
        recording.status = RecordingStatus.PROCESSING
        self.db.flush()
        return recording

    # ------------------------------------------------------------ transcribe
    def _audio(self, recording: MeetingRecording) -> AudioSource:
        storage = self.storage
        key = recording.storage_key
        return AudioSource(
            content_type=recording.content_type or "audio/webm",
            size_bytes=recording.size_bytes,
            url=storage.presigned_url(key),
            open=lambda: storage.open(key),
            path=storage.local_path(key),
        )

    def submit(self, recording: MeetingRecording) -> MeetingRecording:
        provider = self.provider
        if provider is None or not provider.is_configured:
            return self._fail(recording, "Transcription is not configured on the server. The audio is saved — "
                                         "retry once a transcription provider key is set.")
        recording.provider = provider.name
        recording.attempts = (recording.attempts or 0) + 1
        recording.submitted_at = _now()
        recording.provider_job_id = None
        recording.error = None
        recording.status = RecordingStatus.PROCESSING
        self.db.commit()
        try:
            submitted = provider.submit(self._audio(recording))
        except TranscriptionError as exc:
            return self._fail(recording, exc.user_message)
        except StorageError as exc:
            return self._fail(recording, str(exc))
        if submitted.result is not None:
            return self._complete(recording, submitted.result, job_id=None)
        recording.provider_job_id = submitted.job_id
        self.db.commit()
        return recording

    def poll(self, recording: MeetingRecording) -> MeetingRecording:
        provider = self.provider
        if provider is None or provider.name != recording.provider or not recording.provider_job_id:
            return recording
        try:
            result = provider.poll(recording.provider_job_id)
        except TranscriptionError as exc:
            if exc.retryable:
                return recording  # try again next poll
            return self._fail(recording, exc.user_message)
        if result.state == "completed" and result.result is not None:
            return self._complete(recording, result.result, job_id=recording.provider_job_id)
        if result.state == "failed":
            return self._fail(recording, result.error or "Transcription failed.")
        return recording

    def _complete(self, recording: MeetingRecording, result: TranscriptResult, *, job_id: str | None) -> MeetingRecording:
        if not result.segments:
            return self._fail(recording, "No speech was detected in this recording.")
        transcript = recording.transcript or MeetingTranscript(recording_id=recording.id, meeting_id=recording.meeting_id)
        transcript.provider = recording.provider or "unknown"
        transcript.language = result.language
        transcript.text = result.text
        transcript.segments = [
            {"speaker": s.speaker, "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text}
            for s in result.segments
        ]
        transcript.speaker_count = result.speaker_count
        transcript.duration_seconds = result.duration_seconds or recording.duration_seconds
        recording.transcript = transcript
        if result.duration_seconds:
            recording.duration_seconds = result.duration_seconds
        recording.status = RecordingStatus.COMPLETED
        recording.completed_at = _now()
        recording.error = None
        self.db.commit()
        if job_id and self.provider is not None:
            self.provider.cleanup(job_id)
        return recording

    def _fail(self, recording: MeetingRecording, message: str) -> MeetingRecording:
        recording.status = RecordingStatus.FAILED
        recording.error = message
        self.db.commit()
        logger.info("Recording %s failed: %s", recording.id, message)
        return recording

    # ---------------------------------------------------------------- delete
    def delete(self, recording: MeetingRecording) -> None:
        if recording.storage_key:
            try:
                self.storage.delete(recording.storage_key)
            except StorageError as exc:
                raise RecordingError("The audio file could not be deleted from storage. Please try again.", 502) from exc
        self.db.delete(recording)
        self.db.flush()


# ------------------------------------------------------------ job entrypoints
def process_recording_job(recording_id) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        recording = db.get(MeetingRecording, recording_id)
        if recording is not None and recording.status == RecordingStatus.PROCESSING:
            RecordingService(db).submit(recording)
    finally:
        db.close()


def poll_pending_recordings(db: Session | None = None, service: RecordingService | None = None) -> int:
    """Periodic: advance async jobs and recover work a restart interrupted.
    Returns how many recordings were looked at."""
    from app.db.session import SessionLocal

    own_session = db is None
    db = db or SessionLocal()
    try:
        service = service or RecordingService(db)
        now = _now()
        rows = db.query(MeetingRecording).filter(
            MeetingRecording.status.in_([RecordingStatus.PROCESSING, RecordingStatus.UPLOADING])
        ).all()
        for recording in rows:
            if recording.status == RecordingStatus.UPLOADING:
                if now - recording.created_at > UPLOAD_ABANDONED_AFTER:
                    service._fail(recording, "The upload did not finish. Please record or upload again.")
                continue
            if recording.provider_job_id:
                service.poll(recording)
            elif recording.submitted_at is None or now - recording.updated_at > STUCK_AFTER:
                # Never submitted, or a synchronous provider call died with
                # the process — resubmit, a bounded number of times.
                if (recording.attempts or 0) >= MAX_ATTEMPTS:
                    service._fail(recording, "Transcription did not finish after several attempts.")
                elif recording.submitted_at is None and now - recording.updated_at < timedelta(minutes=2):
                    continue  # just uploaded; its own job is about to submit it
                else:
                    service.submit(recording)
        return len(rows)
    finally:
        if own_session:
            db.close()
