"""AssemblyAI pre-recorded transcription (default provider).

Chosen for v1 because it takes a whole meeting in one request (up to 10 h /
5 GB from a URL — no chunking), has mature speaker diarization
(``speaker_labels``), and is asynchronous with a polling endpoint, so a
transcript is never lost to a missed callback or a server restart.

Flow: POST /v2/transcript {audio_url, speaker_labels} -> poll
GET /v2/transcript/{id} -> on completion, read ``utterances`` -> DELETE the
transcript at AssemblyAI (ASSEMBLYAI_DELETE_AFTER_COMPLETE).
With S3 storage, audio_url is a short-lived presigned URL; with local
storage the bytes are uploaded to /v2/upload first.

Docs: https://www.assemblyai.com/docs/pre-recorded-audio/speaker-diarization
      https://www.assemblyai.com/docs/deployment/webhooks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.services.transcription.provider import (
    AudioSource,
    PollResult,
    SpeakerNumbering,
    SubmitResult,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptResult,
    TranscriptSegment,
    plain_text,
)

logger = logging.getLogger("app.transcription")
BASE_URL = "https://api.assemblyai.com"


@dataclass
class AssemblyAIProvider(TranscriptionProvider):
    http: httpx.Client | None = None

    def __post_init__(self) -> None:
        self.name = "assemblyai"
        settings = get_settings()
        self.api_key = settings.assemblyai_api_key.strip()
        self.delete_after = settings.assemblyai_delete_after_complete
        self.http = self.http or httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(60.0, write=600.0))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_assemblyai_api_key"

    def _headers(self) -> dict:
        return {"authorization": self.api_key}  # AssemblyAI: raw key, no "Bearer"

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            res = self.http.request(method, path, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise TranscriptionError("Could not reach the transcription service.", retryable=True) from exc
        if res.status_code == 401:
            raise TranscriptionError("The transcription service rejected the API key (ASSEMBLYAI_API_KEY).")
        if res.status_code == 429 or res.status_code >= 500:
            raise TranscriptionError(f"The transcription service is unavailable (HTTP {res.status_code}).", retryable=True)
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.status_code >= 400:
            logger.warning("AssemblyAI %s %s -> %s %s", method, path, res.status_code, body.get("error"))
            raise TranscriptionError(f"The transcription service refused the request: {body.get('error') or res.status_code}")
        return body

    def submit(self, audio: AudioSource) -> SubmitResult:
        audio_url = audio.url
        if audio_url is None:
            if audio.open is None:
                raise TranscriptionError("Recording audio is not available.")
            with audio.open() as fh:
                audio_url = self._call("POST", "/v2/upload", content=fh)["upload_url"]
        body = self._call("POST", "/v2/transcript", json={
            "audio_url": audio_url,
            "speaker_labels": True,
            "punctuate": True,
            "format_text": True,
        })
        return SubmitResult(job_id=body["id"])

    def poll(self, job_id: str) -> PollResult:
        body = self._call("GET", f"/v2/transcript/{job_id}")
        status = body.get("status")
        if status in ("queued", "processing"):
            return PollResult(state="processing")
        if status == "error":
            return PollResult(state="failed", error=f"Transcription failed: {body.get('error') or 'unknown error'}")
        if status != "completed":
            return PollResult(state="processing")
        return PollResult(state="completed", result=self.parse(body))

    @staticmethod
    def parse(body: dict) -> TranscriptResult:
        speaker = SpeakerNumbering()
        segments = [
            TranscriptSegment(
                speaker=speaker(u.get("speaker")),
                start=(u.get("start") or 0) / 1000,
                end=(u.get("end") or 0) / 1000,
                text=(u.get("text") or "").strip(),
            )
            for u in body.get("utterances") or []
            if (u.get("text") or "").strip()
        ]
        if not segments and (body.get("text") or "").strip():
            segments = [TranscriptSegment(speaker="1", start=0.0, end=float(body.get("audio_duration") or 0), text=body["text"].strip())]
        return TranscriptResult(
            text=plain_text(segments),
            segments=segments,
            language=body.get("language_code"),
            duration_seconds=float(body["audio_duration"]) if body.get("audio_duration") else None,
        )

    def cleanup(self, job_id: str) -> None:
        if not self.delete_after:
            return
        try:
            self._call("DELETE", f"/v2/transcript/{job_id}")
        except TranscriptionError as exc:
            logger.warning("Could not delete AssemblyAI transcript %s: %s", job_id, exc.user_message)
