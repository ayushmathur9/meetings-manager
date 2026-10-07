"""OpenAI speech-to-text with diarization (alternative provider).

Uses ``gpt-4o-transcribe-diarize`` with ``response_format=diarized_json``.
Limitation: OpenAI accepts at most 25 MB per request and long audio is
capped per request, so this provider refuses recordings over 25 MB rather
than silently chunking them (chunking would need speaker labels stitched
across chunks). Prefer AssemblyAI or Deepgram for long meetings.

Docs: https://developers.openai.com/api/docs/guides/speech-to-text
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.services.transcription.provider import (
    AudioSource,
    SpeakerNumbering,
    SubmitResult,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptResult,
    TranscriptSegment,
    plain_text,
)

URL = "https://api.openai.com/v1/audio/transcriptions"
MODEL = "gpt-4o-transcribe-diarize"
MAX_BYTES = 25 * 1024 * 1024
_EXTENSIONS = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav",
               "audio/x-m4a": "m4a", "audio/ogg": "ogg"}


@dataclass
class OpenAIProvider(TranscriptionProvider):
    http: httpx.Client | None = None

    def __post_init__(self) -> None:
        self.name = "openai"
        self.api_key = get_settings().openai_api_key.strip()
        self.http = self.http or httpx.Client(timeout=httpx.Timeout(900.0, connect=30.0))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_openai_api_key"

    def submit(self, audio: AudioSource) -> SubmitResult:
        if audio.size_bytes and audio.size_bytes > MAX_BYTES:
            raise TranscriptionError(
                "This recording is larger than OpenAI's 25 MB limit. Switch TRANSCRIPTION_PROVIDER to "
                "assemblyai or deepgram for long meetings."
            )
        if audio.open is None:
            raise TranscriptionError("Recording audio is not available.")
        with audio.open() as fh:
            data = fh.read()
        filename = f"meeting.{_EXTENSIONS.get(audio.content_type, 'webm')}"
        try:
            res = self.http.post(
                URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={"model": MODEL, "response_format": "diarized_json", "chunking_strategy": "auto"},
                files={"file": (filename, data, audio.content_type)},
            )
        except httpx.HTTPError as exc:
            raise TranscriptionError("Could not reach the transcription service.", retryable=True) from exc
        if res.status_code == 401:
            raise TranscriptionError("The transcription service rejected the API key (OPENAI_API_KEY).")
        if res.status_code == 429 or res.status_code >= 500:
            raise TranscriptionError(f"The transcription service is unavailable (HTTP {res.status_code}).", retryable=True)
        if res.status_code >= 400:
            try:
                detail = res.json().get("error", {}).get("message")
            except ValueError:
                detail = None
            raise TranscriptionError(f"The transcription service refused the audio: {detail or res.status_code}")
        return SubmitResult(result=self.parse(res.json()))

    @staticmethod
    def parse(body: dict) -> TranscriptResult:
        speaker = SpeakerNumbering()
        segments = [
            TranscriptSegment(speaker=speaker(s.get("speaker")), start=float(s.get("start") or 0),
                              end=float(s.get("end") or 0), text=(s.get("text") or "").strip())
            for s in body.get("segments") or []
            if (s.get("text") or "").strip()
        ]
        duration = body.get("duration")
        return TranscriptResult(text=plain_text(segments), segments=segments, language=body.get("language"),
                                duration_seconds=float(duration) if duration else None)
