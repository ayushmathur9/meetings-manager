"""Meeting recordings: upload, storage privacy, permissions, transcription
job lifecycle (async + sync providers), failure/retry, provider parsers."""

import io
from datetime import date, time

import httpx
import pytest

from app.models.company import Company
from app.models.meeting import Meeting
from app.models.recording import MeetingRecording, RecordingStatus
from app.services import background
from app.services.recording_service import RecordingService, poll_pending_recordings
from app.services.storage import LocalStorage, set_storage
from app.services.transcription import PollResult, SubmitResult, TranscriptionError, TranscriptResult, TranscriptSegment
from app.services.transcription.assemblyai_provider import AssemblyAIProvider
from app.services.transcription.deepgram_provider import DeepgramProvider
from app.services.transcription.openai_provider import OpenAIProvider
from app.services.transcription.provider import AudioSource

AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048  # WebM magic + padding


class FakeAsyncProvider:
    name = "fake_async"
    is_configured = True

    def __init__(self):
        self.submitted = []
        self.polls = 0
        self.cleaned = []
        self.outcome = "completed"

    def submit(self, audio):
        with audio.open() as fh:
            self.submitted.append(fh.read())
        return SubmitResult(job_id="job-1")

    def poll(self, job_id):
        self.polls += 1
        if self.polls == 1:
            return PollResult(state="processing")
        if self.outcome == "failed":
            return PollResult(state="failed", error="Transcription failed: audio unreadable")
        segments = [TranscriptSegment("1", 0.0, 3.5, "Thanks for meeting with us."),
                    TranscriptSegment("2", 3.6, 6.0, "Happy to, tell me about your IT support.")]
        return PollResult(state="completed", result=TranscriptResult(
            text="Speaker 1: ...", segments=segments, language="en", duration_seconds=2538.0))

    def cleanup(self, job_id):
        self.cleaned.append(job_id)


@pytest.fixture
def storage(tmp_path):
    store = LocalStorage(str(tmp_path / "store"))
    set_storage(store)
    yield store
    set_storage(None)


@pytest.fixture
def queued(monkeypatch):
    jobs = []
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: jobs.append(a))
    return jobs


@pytest.fixture
def meeting(db, sales_user, admin_user):
    company = Company(name="Eastern Dermatology", normalized_name="eastern dermatology")
    db.add(company)
    db.flush()
    m = Meeting(company_id=company.id, salesperson_id=sales_user.id, created_by_id=admin_user.id,
                date=date(2026, 10, 12), start_time=time(10, 0), end_time=time(10, 25), duration_minutes=25)
    db.add(m)
    db.commit()
    return m


def upload(client, meeting_id, *, content_type="audio/webm;codecs=opus", data=AUDIO):
    return client.post(f"/meetings/{meeting_id}/recordings",
                       files={"file": ("meeting.webm", io.BytesIO(data), content_type)},
                       data={"duration_seconds": "2541.2"})


def test_upload_stores_privately_and_queues_transcription(db, meeting, sales_client, storage, queued):
    res = upload(sales_client, meeting.id)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "processing" and body["duration_seconds"] == 2541.2 and body["can_delete"]
    rec = db.get(MeetingRecording, body["id"])
    assert rec.storage_key == f"recordings/{meeting.id}/{rec.id}.webm" and rec.content_type == "audio/webm"
    assert storage.local_path(rec.storage_key).read_bytes() == AUDIO
    assert queued == [(rec.id,)]


def test_async_transcription_lifecycle(db, meeting, sales_client, storage, queued):
    rec_id = upload(sales_client, meeting.id).json()["id"]
    provider = FakeAsyncProvider()
    service = RecordingService(db, storage, provider)
    rec = db.get(MeetingRecording, rec_id)

    service.submit(rec)
    assert provider.submitted == [AUDIO] and rec.provider_job_id == "job-1"
    poll_pending_recordings(db, service)
    assert rec.status == RecordingStatus.PROCESSING  # still processing
    poll_pending_recordings(db, service)
    assert rec.status == RecordingStatus.COMPLETED and provider.cleaned == ["job-1"]

    listed = sales_client.get(f"/meetings/{meeting.id}/recordings").json()[0]
    t = listed["transcript"]
    assert listed["duration_seconds"] == 2538.0 and t["speaker_count"] == 2
    assert [s["speaker"] for s in t["segments"]] == ["1", "2"]
    txt = sales_client.get(f"/recordings/{rec_id}/transcript.txt")
    assert txt.status_code == 200 and "attachment" in txt.headers["content-disposition"]
    assert "Duration: 42:18" in txt.text and "[00:03] Speaker 2:\nHappy to" in txt.text


def test_failed_transcript_and_retry(db, meeting, sales_client, storage, queued):
    rec_id = upload(sales_client, meeting.id).json()["id"]
    provider = FakeAsyncProvider()
    provider.outcome = "failed"
    service = RecordingService(db, storage, provider)
    rec = db.get(MeetingRecording, rec_id)
    service.submit(rec)
    poll_pending_recordings(db, service)
    poll_pending_recordings(db, service)
    assert rec.status == RecordingStatus.FAILED and "unreadable" in rec.error

    res = sales_client.post(f"/recordings/{rec_id}/retry")
    assert res.status_code == 202 and res.json()["status"] == "processing" and len(queued) == 2


def test_transcription_not_configured_fails_honestly(db, meeting, sales_client, storage, queued):
    rec_id = upload(sales_client, meeting.id).json()["id"]

    class Unconfigured(FakeAsyncProvider):
        is_configured = False

    rec = RecordingService(db, storage, Unconfigured()).submit(db.get(MeetingRecording, rec_id))
    assert rec.status == RecordingStatus.FAILED and "not configured" in rec.error
    assert rec.transcript is None


def test_sync_provider_failure_is_recorded(db, meeting, sales_client, storage, queued):
    rec_id = upload(sales_client, meeting.id).json()["id"]

    class Broken(FakeAsyncProvider):
        def submit(self, audio):
            raise TranscriptionError("The transcription service rejected the API key (DEEPGRAM_API_KEY).")

    rec = RecordingService(db, storage, Broken()).submit(db.get(MeetingRecording, rec_id))
    assert rec.status == RecordingStatus.FAILED and "DEEPGRAM_API_KEY" in rec.error


def test_permissions(db, meeting, sales_client, other_sales_client, admin_client, anon_client, storage, queued):
    rec_id = upload(sales_client, meeting.id).json()["id"]

    # Another salesperson can't start, list, read, play, download or delete.
    assert upload(other_sales_client, meeting.id).status_code == 404
    assert other_sales_client.get(f"/meetings/{meeting.id}/recordings").status_code == 404
    for path in (f"/recordings/{rec_id}", f"/recordings/{rec_id}/audio", f"/recordings/{rec_id}/transcript.txt"):
        assert other_sales_client.get(path).status_code == 404
        assert anon_client.get(path).status_code == 401
    assert other_sales_client.delete(f"/recordings/{rec_id}").status_code == 404

    # Admins can access everything.
    assert admin_client.get(f"/recordings/{rec_id}").status_code == 200
    audio = admin_client.get(f"/recordings/{rec_id}/audio")
    assert audio.status_code == 200 and audio.content == AUDIO


def test_s3_audio_is_a_short_lived_presigned_redirect(db, meeting, sales_client, queued):
    class FakeS3:
        name = "s3"

        def __init__(self):
            self.objects = {}

        def put(self, key, fileobj, content_type):
            self.objects[key] = fileobj.read()

        def presigned_url(self, key, *, download_name=None):
            return f"https://bucket.example/{key}?X-Amz-Expires=900&X-Amz-Signature=abc"

        def local_path(self, key):
            return None

        def delete(self, key):
            self.objects.pop(key)

    s3 = FakeS3()
    set_storage(s3)
    try:
        rec_id = upload(sales_client, meeting.id).json()["id"]
        res = sales_client.get(f"/recordings/{rec_id}/audio", follow_redirects=False)
        assert res.status_code == 307 and "X-Amz-Signature" in res.headers["location"]
        assert sales_client.delete(f"/recordings/{rec_id}").status_code == 204
        assert s3.objects == {}
    finally:
        set_storage(None)


def test_delete_removes_audio_and_row(db, meeting, sales_client, storage, queued):
    rec_id = upload(sales_client, meeting.id).json()["id"]
    key = db.get(MeetingRecording, rec_id).storage_key
    assert sales_client.delete(f"/recordings/{rec_id}").status_code == 204
    assert not storage.local_path(key).exists()
    assert sales_client.get(f"/recordings/{rec_id}").status_code == 404


def test_rejects_non_audio_and_empty_uploads(meeting, sales_client, storage, queued):
    assert upload(sales_client, meeting.id, content_type="application/pdf").status_code == 415
    assert upload(sales_client, meeting.id, data=b"").status_code == 400


# ------------------------------------------------------------- provider parsers


def _audio(data=AUDIO, url=None):
    return AudioSource(content_type="audio/webm", size_bytes=len(data), url=url, open=lambda: io.BytesIO(data))


def test_assemblyai_submit_poll_and_parse():
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.url.path == "/v2/transcript" and request.method == "POST":
            import json

            body = json.loads(request.content)
            assert body["speaker_labels"] is True and body["audio_url"].startswith("https://bucket")
            return httpx.Response(200, json={"id": "t1", "status": "queued"})
        if request.method == "GET":
            return httpx.Response(200, json={
                "status": "completed", "audio_duration": 61, "language_code": "en_us",
                "utterances": [{"speaker": "B", "start": 0, "end": 1500, "text": "Hello."},
                               {"speaker": "A", "start": 1600, "end": 4000, "text": "Hi there."},
                               {"speaker": "B", "start": 4100, "end": 5000, "text": "Shall we start?"}],
            })
        return httpx.Response(200, json={})

    provider = AssemblyAIProvider(http=httpx.Client(base_url="https://api.assemblyai.com",
                                                    transport=httpx.MockTransport(handler)))
    provider.api_key = "aai-key"
    assert provider.submit(_audio(url="https://bucket/x.webm")).job_id == "t1"
    result = provider.poll("t1")
    assert result.state == "completed"
    assert [(s.speaker, s.start) for s in result.result.segments] == [("1", 0.0), ("2", 1.6), ("1", 4.1)]
    assert result.result.duration_seconds == 61.0
    assert calls[0][2] == "aai-key"  # raw key, no "Bearer"


def test_assemblyai_uploads_bytes_when_no_url():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/v2/upload":
            assert request.content == AUDIO
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/upload/abc"})
        return httpx.Response(200, json={"id": "t2"})

    provider = AssemblyAIProvider(http=httpx.Client(base_url="https://api.assemblyai.com",
                                                    transport=httpx.MockTransport(handler)))
    provider.api_key = "k"
    assert provider.submit(_audio()).job_id == "t2" and paths == ["/v2/upload", "/v2/transcript"]


def test_assemblyai_bad_key_is_not_retryable():
    provider = AssemblyAIProvider(http=httpx.Client(base_url="https://api.assemblyai.com",
                                                    transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    provider.api_key = "bad"
    with pytest.raises(TranscriptionError) as err:
        provider.submit(_audio(url="https://bucket/x"))
    assert not err.value.retryable and "ASSEMBLYAI_API_KEY" in err.value.user_message


def test_deepgram_parse():
    body = {"metadata": {"duration": 12.5}, "results": {"utterances": [
        {"speaker": 0, "start": 0.1, "end": 2.0, "transcript": "Good morning."},
        {"speaker": 1, "start": 2.1, "end": 4.0, "transcript": "Morning!"}]}}
    provider = DeepgramProvider(http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
    provider.api_key = "dg"
    result = provider.submit(_audio(url="https://bucket/x")).result
    assert [s.speaker for s in result.segments] == ["1", "2"] and result.duration_seconds == 12.5


def test_openai_refuses_files_over_25mb_and_parses_diarized_json():
    provider = OpenAIProvider(http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "duration": 9.0, "segments": [{"speaker": "A", "start": 0, "end": 2, "text": "Hi."},
                                      {"speaker": "B", "start": 2, "end": 4, "text": "Hello."}]}))))
    provider.api_key = "sk"
    big = AudioSource(content_type="audio/webm", size_bytes=26 * 1024 * 1024, open=lambda: io.BytesIO(b""))
    with pytest.raises(TranscriptionError, match="25 MB"):
        provider.submit(big)
    result = provider.submit(_audio()).result
    assert [s.speaker for s in result.segments] == ["1", "2"]
