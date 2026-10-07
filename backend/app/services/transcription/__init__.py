from app.services.transcription.provider import (
    AudioSource,
    PollResult,
    SubmitResult,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptResult,
    TranscriptSegment,
)

__all__ = [
    "AudioSource",
    "PollResult",
    "SubmitResult",
    "TranscriptionError",
    "TranscriptionProvider",
    "TranscriptResult",
    "TranscriptSegment",
    "get_transcription_provider",
]


def get_transcription_provider() -> TranscriptionProvider | None:
    """The provider selected by TRANSCRIPTION_PROVIDER, or None ("none")."""
    from app.core.config import get_settings

    name = get_settings().transcription_provider.strip().lower()
    if name == "assemblyai":
        from app.services.transcription.assemblyai_provider import AssemblyAIProvider

        return AssemblyAIProvider()
    if name == "deepgram":
        from app.services.transcription.deepgram_provider import DeepgramProvider

        return DeepgramProvider()
    if name == "openai":
        from app.services.transcription.openai_provider import OpenAIProvider

        return OpenAIProvider()
    return None
