"""Provider-neutral speech-to-text interface.

The rest of the app only sees ``TranscriptionProvider`` and
``TranscriptResult``; swapping AssemblyAI for Deepgram or OpenAI is a
config change (TRANSCRIPTION_PROVIDER).

Two provider shapes are supported:
  * asynchronous (AssemblyAI): ``submit`` returns a job id, and the
    transcription poller calls ``poll`` until the job finishes — which
    survives server restarts, since the job id is stored on the recording;
  * synchronous (Deepgram, OpenAI): ``submit`` blocks (in a background
    thread) and returns the finished transcript directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Callable


class TranscriptionError(Exception):
    """``user_message`` is safe to show in the UI; it never contains keys."""

    def __init__(self, user_message: str, *, retryable: bool = False) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable


@dataclass
class AudioSource:
    content_type: str
    size_bytes: int | None
    # A time-limited URL the provider can fetch (S3 storage), when available.
    url: str | None = None
    # Otherwise the provider uploads the bytes itself.
    open: Callable[[], BinaryIO] | None = None
    path: Path | None = None


@dataclass
class TranscriptSegment:
    speaker: str  # "1", "2", ... in order of first appearance
    start: float  # seconds
    end: float
    text: str


@dataclass
class TranscriptResult:
    text: str
    segments: list[TranscriptSegment]
    language: str | None = None
    duration_seconds: float | None = None

    @property
    def speaker_count(self) -> int:
        return len({s.speaker for s in self.segments})


@dataclass
class SubmitResult:
    job_id: str | None = None
    result: TranscriptResult | None = None


@dataclass
class PollResult:
    state: str  # "processing" | "completed" | "failed"
    result: TranscriptResult | None = None
    error: str | None = None


class SpeakerNumbering:
    """Maps provider labels ("A", 0, "speaker_1") to "1", "2", ... in order
    of first appearance — consistent across providers, and never a guess at
    who the person is."""

    def __init__(self) -> None:
        self._labels: dict[str, str] = {}

    def __call__(self, raw) -> str:
        key = str(raw)
        if key not in self._labels:
            self._labels[key] = str(len(self._labels) + 1)
        return self._labels[key]


@dataclass
class TranscriptionProvider(ABC):
    name: str = field(init=False, default="")

    @property
    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def submit(self, audio: AudioSource) -> SubmitResult: ...

    def poll(self, job_id: str) -> PollResult:
        raise NotImplementedError(f"{self.name} transcribes synchronously")

    def cleanup(self, job_id: str) -> None:
        """Delete provider-side copies once the transcript is stored."""


def plain_text(segments: list[TranscriptSegment]) -> str:
    return "\n\n".join(f"Speaker {s.speaker}: {s.text}" for s in segments)
