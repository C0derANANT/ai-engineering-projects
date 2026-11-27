"""Tests for the prompt in brochure/generator.py (no AI call is made)."""

from types import SimpleNamespace

import httpx
import openai
import pytest

from brochure import generator
from brochure.generator import BrochureError, BrochureRequest, _build_messages, stream_brochure
from brochure.scraper import WebsiteContext


def test_prompt_asks_for_the_website_first_in_get_in_touch():
    request = BrochureRequest("Acme", website=WebsiteContext(url="https://acme.test"))
    system, user = (message["content"] for message in _build_messages(request))
    assert '"- **Website:** [example.com](https://example.com)"' in system
    assert "Never invent phone numbers" in system
    assert "Website: https://acme.test" in user  # the address the AI is told to use


def test_prompt_without_a_website_says_so():
    system, user = (message["content"] for message in _build_messages(BrochureRequest("Acme")))
    assert "No website was provided." in user


# --------------------------------------------------------------------------
# Streaming and the Groq -> Gemini fallback (fake clients, no network)
# --------------------------------------------------------------------------
def api_error(status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.test/chat"))
    return openai.APIStatusError(f"HTTP {status}", response=response, body={"error": {"message": "nope"}})


def chunk(text: str, finish: str | None = None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish)])


class FakeStream(list):
    def close(self):
        pass


class FakeOpenAI:
    """Replies per base URL: a list of chunks, or an exception to raise."""

    script: dict = {}
    calls: list = []

    def __init__(self, base_url, api_key, timeout, max_retries):
        self.base_url, self.max_retries = base_url, max_retries
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, model, **kwargs):
        FakeOpenAI.calls.append((self.base_url, model, self.max_retries))
        reply = FakeOpenAI.script[self.base_url]
        if isinstance(reply, Exception):
            raise reply
        return FakeStream(reply)


GROQ, GEMINI = "https://groq.test", "https://gemini.test"
BROCHURE = [chunk("# Acme\n"), chunk("*Rockets.*\n\n## About Us\nWe fly."), chunk("", "stop")]


@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GROQ_BASE_URL", GROQ)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("GEMINI_BASE_URL", GEMINI)
    monkeypatch.setattr(generator, "OpenAI", FakeOpenAI)
    FakeOpenAI.calls = []
    return FakeOpenAI


def test_streams_the_brochure(providers):
    providers.script = {GROQ: BROCHURE}
    parts = list(stream_brochure(BrochureRequest("Acme")))
    assert parts[-1].endswith("We fly.") and len(parts) >= 2
    assert [call[0] for call in providers.calls] == [GROQ]


@pytest.mark.parametrize("error", [api_error(429), api_error(503), openai.APIConnectionError(
    request=httpx.Request("POST", GROQ))])
def test_busy_groq_hands_over_to_gemini(providers, error):
    providers.script = {GROQ: error, GEMINI: BROCHURE}
    warnings = []
    parts = list(stream_brochure(BrochureRequest("Acme"), on_warning=warnings.append))
    assert parts[-1].endswith("We fly.")
    assert [call[0] for call in providers.calls] == [GROQ, GEMINI]
    assert providers.calls[0][2] == 0  # no waiting out the rate limit when a backup exists
    assert "Gemini is writing" in warnings[0]


def test_a_bad_key_is_reported_not_hidden_by_the_fallback(providers):
    providers.script = {GROQ: api_error(401), GEMINI: BROCHURE}
    with pytest.raises(BrochureError, match="rejected the API key"):
        list(stream_brochure(BrochureRequest("Acme")))
    assert len(providers.calls) == 1


def test_no_fallback_when_a_provider_is_chosen(providers):
    providers.script = {GROQ: api_error(429), GEMINI: BROCHURE}
    with pytest.raises(BrochureError, match="rate limit"):
        list(stream_brochure(BrochureRequest("Acme", provider="Groq")))


def test_both_busy_gives_the_last_error(providers):
    providers.script = {GROQ: api_error(429), GEMINI: api_error(503)}
    with pytest.raises(BrochureError, match="Gemini is having problems"):
        list(stream_brochure(BrochureRequest("Acme")))


def test_a_stream_cut_off_midway_is_an_error(providers):
    providers.script = {GROQ: [chunk("# Acme\nHalf a brochure")]}  # no finish reason
    with pytest.raises(BrochureError, match="ended before the brochure was finished"):
        list(stream_brochure(BrochureRequest("Acme")))
