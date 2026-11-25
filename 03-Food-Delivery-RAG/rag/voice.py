"""Voice questions: speech to text with Whisper on Groq (understands Hindi, Hinglish and English)."""

from __future__ import annotations

import re
from pathlib import Path

from .config import Settings, get_secret

AUDIO_EXTENSIONS = {".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Groq's upload limit
MIN_AUDIO_BYTES = 2 * 1024  # anything smaller is a click, not speech

# Helps Whisper spell brand words and pick the right languages
WHISPER_HINT = (
    "CraveCart food delivery support. Order, refund, cancel, delivery partner, CraveCart Plus, "
    "CraveCart Money, UPI. Hindi, Hinglish or English."
)


class VoiceError(Exception):
    """A problem with a voice message that the user can fix (shown to them as-is)."""


def is_audio(path) -> bool:
    return Path(str(path)).suffix.lower() in AUDIO_EXTENSIONS


def transcribe(path, settings: Settings, client=None) -> str:
    """Return the text spoken in an audio file, or raise VoiceError with a friendly reason."""
    file = Path(str(path))
    if not file.is_file():
        raise VoiceError("I couldn't find the recording. Please try recording again.")
    if not is_audio(file):
        raise VoiceError("I can only listen to audio recordings (for example .wav, .mp3, .m4a or .webm).")
    size = file.stat().st_size
    if size < MIN_AUDIO_BYTES:
        raise VoiceError("The recording was empty or too short. Please hold the mic and speak your question.")
    if size > MAX_AUDIO_BYTES:
        raise VoiceError("That recording is too long (over 25 MB). Please keep voice questions under a minute or two.")

    if client is None:
        key = get_secret("GROQ_API_KEY")
        if not key:
            raise VoiceError("Voice questions need a GROQ_API_KEY. Please type your question instead.")
        from groq import Groq

        client = Groq(api_key=key, timeout=settings.llm_timeout_seconds, max_retries=1)

    try:
        with file.open("rb") as handle:
            result = client.audio.transcriptions.create(
                file=(file.name, handle.read()),
                model=settings.whisper_model,
                prompt=WHISPER_HINT,
                temperature=0,
            )
    except Exception as exc:  # network, rate limit, bad format
        from .llm import describe_error

        raise VoiceError(f"I couldn't understand the recording: {describe_error(exc)}") from exc

    text = (getattr(result, "text", None) or "").strip()
    if _is_silence(text):
        raise VoiceError("I couldn't hear a question in that recording. Please try again closer to the mic.")
    return text


# Phrases Whisper invents for silent audio
_SILENCE_PHRASES = {"thank you", "thanks for watching", "thank you for watching", "you", "bye", "subtitles by"}


def _normalise(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _is_silence(text: str) -> bool:
    """Empty output, a stock phrase, or just words echoed from our own hint all mean nobody spoke."""
    words = _normalise(text)
    return not words or words in _SILENCE_PHRASES or words in _normalise(WHISPER_HINT)
