"""Deepgram Nova-3 pre-recorded transcription (alternative provider).

Synchronous: one POST /v1/listen returns the finished transcript (Deepgram
processes up to 10 minutes per request, ample for a 90-minute file). It runs
inside a background job, never an HTTP request. Diarization via
``diarize_model=latest`` + ``utterances=true``; ``mip_opt_out=true`` keeps
audio out of Deepgram's model-improvement program.

Docs: https://developers.deepgram.com/docs/pre-recorded-audio
      https://developers.deepgram.com/docs/diarization
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

LISTEN_URL = "https://api.deepgram.com/v1/listen"
PARAMS = {
    "model": "nova-3",
    "diarize_model": "latest",
    "utterances": "true",
    "smart_format": "true",
    "punctuate": "true",
    "mip_opt_out": "true",
}


@dataclass
class DeepgramProvider(TranscriptionProvider):
    http: httpx.Client | None = None

    def __post_init__(self) -> None:
        self.name = "deepgram"
        self.api_key = get_settings().deepgram_api_key.strip()
        self.http = self.http or httpx.Client(timeout=httpx.Timeout(700.0, connect=30.0))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_deepgram_api_key"

    def submit(self, audio: AudioSource) -> SubmitResult:
        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            if audio.url:
                res = self.http.post(LISTEN_URL, params=PARAMS, headers=headers, json={"url": audio.url})
            elif audio.open:
                with audio.open() as fh:
                    res = self.http.post(LISTEN_URL, params=PARAMS, headers={**headers, "Content-Type": audio.content_type},
                                         content=fh.read())
            else:
                raise TranscriptionError("Recording audio is not available.")
        except httpx.HTTPError as exc:
            raise TranscriptionError("Could not reach the transcription service.", retryable=True) from exc
        if res.status_code == 401:
            raise TranscriptionError("The transcription service rejected the API key (DEEPGRAM_API_KEY).")
        if res.status_code == 429 or res.status_code >= 500:
            raise TranscriptionError(f"The transcription service is unavailable (HTTP {res.status_code}).", retryable=True)
        if res.status_code >= 400:
            raise TranscriptionError(f"The transcription service refused the audio (HTTP {res.status_code}).")
        return SubmitResult(result=self.parse(res.json()))

    @staticmethod
    def parse(body: dict) -> TranscriptResult:
        speaker = SpeakerNumbering()
        results = body.get("results") or {}
        segments = [
            TranscriptSegment(speaker=speaker(u.get("speaker", 0)), start=float(u.get("start") or 0),
                              end=float(u.get("end") or 0), text=(u.get("transcript") or "").strip())
            for u in results.get("utterances") or []
            if (u.get("transcript") or "").strip()
        ]
        duration = (body.get("metadata") or {}).get("duration")
        channels = results.get("channels") or [{}]
        language = (channels[0] or {}).get("detected_language")
        return TranscriptResult(text=plain_text(segments), segments=segments, language=language,
                                duration_seconds=float(duration) if duration else None)
