from types import SimpleNamespace

import gradio as gr
import pytest

import app
from movie import voice
from movie.assistant import HEARD_PREFIX, Reply
from movie.config import Settings, server_options
from movie.voice import VoiceError, is_audio, transcribe


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


def test_transcribes_with_the_hint(recording):
    client = FakeWhisper(text="  Pathaan ka budget kitna tha?  ")
    assert transcribe(recording, Settings(), client=client) == "Pathaan ka budget kitna tha?"
    assert client.sent["model"] == Settings().whisper_model and "movie" in client.sent["prompt"]


@pytest.mark.parametrize("text", ["", "  ", "Thank you.", "Thanks for watching!", "Hindi, Hinglish or English."])
def test_silence_is_reported(recording, text):
    with pytest.raises(VoiceError, match="couldn't hear"):
        transcribe(recording, Settings(), client=FakeWhisper(text=text))


def test_api_failure_is_friendly(recording):
    with pytest.raises(VoiceError, match="couldn't understand"):
        transcribe(recording, Settings(), client=FakeWhisper(error=RuntimeError("x")))


def test_bad_files(tmp_path):
    with pytest.raises(VoiceError, match="couldn't find"):
        transcribe(tmp_path / "missing.wav", Settings(), client=FakeWhisper(text="x"))
    image = tmp_path / "poster.png"
    image.write_bytes(b"x" * 5000)
    with pytest.raises(VoiceError, match="audio"):
        transcribe(image, Settings(), client=FakeWhisper(text="x"))
    tiny = tmp_path / "tiny.wav"
    tiny.write_bytes(b"x" * 100)
    with pytest.raises(VoiceError, match="too short"):
        transcribe(tiny, Settings(), client=FakeWhisper(text="x"))


def test_too_large_file(recording, monkeypatch):
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 1000)
    with pytest.raises(VoiceError, match="too long"):
        transcribe(recording, Settings(), client=FakeWhisper(text="x"))


def test_needs_a_groq_key(recording, monkeypatch):
    monkeypatch.setattr(voice, "get_secret", lambda name: None)
    with pytest.raises(VoiceError, match="GROQ_API_KEY"):
        transcribe(recording, Settings())


def test_is_audio():
    assert is_audio("a.WAV") and is_audio("/x/y.webm") and not is_audio("a.png")


# ---- the Gradio app ---------------------------------------------------------------------------
def test_app_builds():
    assert isinstance(app.demo, gr.Blocks)


def test_split_message():
    assert app.split_message("  hi ") == ("hi", [])
    assert app.split_message(None) == ("", [])
    assert app.split_message({"text": " q ", "files": ["/a.wav", {"path": "/b.webm"}, {"x": 1}]}) == (
        "q", ["/a.wav", "/b.webm"]
    )


def test_voice_question_flows_into_the_answer(monkeypatch, recording):
    monkeypatch.setattr(app, "transcribe", lambda path, settings: "Sholay ka director?")
    asked = []

    def fake_respond(text, history):
        asked.append(text)
        yield Reply("Ramesh Sippy.", done=True)

    monkeypatch.setattr(app.assistant, "respond", fake_respond)
    out = list(app.respond({"text": "", "files": [str(recording)]}, []))
    assert asked == ["Sholay ka director?"]
    assert out[-1] == f"{HEARD_PREFIX}Sholay ka director?”\n\nRamesh Sippy."


def test_voice_problems_are_shown(monkeypatch, recording):
    def deaf(path, settings):
        raise VoiceError("I couldn't hear a question.")

    monkeypatch.setattr(app, "transcribe", deaf)
    assert list(app.respond({"text": "", "files": [str(recording)]}, [])) == ["🎙️ I couldn't hear a question."]


def test_non_audio_upload_without_text():
    out = list(app.respond({"text": "", "files": ["/tmp/poster.png"]}, []))
    assert "text and voice recordings" in out[0]


# ---- hosting ----------------------------------------------------------------------------------
def test_listens_on_render_port():
    assert server_options({"PORT": "10000"}) == {"server_name": "0.0.0.0", "server_port": 10000}


@pytest.mark.parametrize("environ", [{}, {"PORT": ""}, {"PORT": "abc"}, {"PORT": "0"}, {"PORT": "70000"}])
def test_keeps_gradio_defaults_without_a_valid_port(environ):
    assert server_options(environ) == {}
