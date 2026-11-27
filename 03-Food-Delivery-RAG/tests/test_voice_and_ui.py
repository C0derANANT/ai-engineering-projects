from types import SimpleNamespace

import pytest

from rag import voice
from rag.assistant import Reply
from rag.config import server_options
from rag.ui import EMPTY_SOURCES, sources_markdown, split_message
from rag.voice import VoiceError, is_audio, transcribe

from .conftest import make_hits


class FakeWhisper:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.sent = text, error, None
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.sent = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / "question.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 8000)
    return path


def test_transcribes_with_the_hint(settings, recording):
    client = FakeWhisper(text="  mera order kab aayega  ")
    assert transcribe(recording, settings, client=client) == "mera order kab aayega"
    assert client.sent["model"] == settings.whisper_model and "CraveCart" in client.sent["prompt"]


@pytest.mark.parametrize(
    "text", ["", "   ", "Thank you.", "Thanks for watching!", "...", "Hinglish or English.", "CraveCart food delivery support."]
)
def test_silence_is_reported(settings, recording, text):
    with pytest.raises(VoiceError, match="couldn't hear"):
        transcribe(recording, settings, client=FakeWhisper(text=text))


def test_api_failure_is_friendly(settings, recording):
    class Boom(Exception):
        status_code = 429

    with pytest.raises(VoiceError, match="busy"):
        transcribe(recording, settings, client=FakeWhisper(error=Boom("x")))


def test_bad_files(settings, tmp_path):
    with pytest.raises(VoiceError, match="couldn't find"):
        transcribe(tmp_path / "missing.wav", settings, client=FakeWhisper(text="x"))
    image = tmp_path / "photo.png"
    image.write_bytes(b"x" * 5000)
    with pytest.raises(VoiceError, match="audio"):
        transcribe(image, settings, client=FakeWhisper(text="x"))
    tiny = tmp_path / "tiny.wav"
    tiny.write_bytes(b"x" * 100)
    with pytest.raises(VoiceError, match="too short"):
        transcribe(tiny, settings, client=FakeWhisper(text="x"))


def test_too_large_file(settings, recording, monkeypatch):
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 1000)
    with pytest.raises(VoiceError, match="too long"):
        transcribe(recording, settings, client=FakeWhisper(text="x"))


def test_needs_a_groq_key(settings, recording, monkeypatch):
    monkeypatch.setattr(voice, "get_secret", lambda name: None)
    with pytest.raises(VoiceError, match="GROQ_API_KEY"):
        transcribe(recording, settings)


def test_is_audio():
    assert is_audio("a.WAV") and is_audio("/x/y.webm") and not is_audio("a.png")


# ---- UI helpers ------------------------------------------------------------------------------
def test_split_message_formats():
    assert split_message("  hi ") == ("hi", [])
    assert split_message(None) == ("", [])
    assert split_message({"text": " q ", "files": ["/a.wav", {"path": "/b.webm"}, {"x": 1}]}) == (
        "q", ["/a.wav", "/b.webm"]
    )


def test_sources_panel():
    assert sources_markdown(None) == EMPTY_SOURCES
    reply = Reply(text="UPI refunds take 1–3 days [2].", hits=make_hits(3), cited={2},
                  tools_used=["cancellation_quote(1042)"], query="refund time", model="fake", done=True)
    panel = sources_markdown(reply)
    assert "Calculated with tools" in panel and "cancellation_quote(1042)" in panel
    cited_part, others = panel.split("Also retrieved")
    assert "[2]** ✅" in cited_part and "[1]**" in others and "[3]**" in others
    assert "refund time" in panel and "fake" in panel


# ---- hosting -------------------------------------------------------------------------------
def test_listens_on_render_port():
    assert server_options({"PORT": "10000"}) == {"server_name": "0.0.0.0", "server_port": 10000}


@pytest.mark.parametrize("environ", [{}, {"PORT": ""}, {"PORT": "abc"}, {"PORT": "0"}, {"PORT": "70000"}])
def test_keeps_gradio_defaults_without_a_valid_port(environ):
    assert server_options(environ) == {}
