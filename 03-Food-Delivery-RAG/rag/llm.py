"""Chat models: Groq first (same model as the class notebooks), Gemini as an optional backup.

Groq's free tier limits tokens per minute. When a Gemini key is set, a rate-limited Groq call
switches to Gemini immediately instead of waiting 10-20 seconds to retry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings, get_secret

log = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Gemini 3 rejects a tool-call history unless each call carries a "thought signature".
# LangChain drops the real one, so we send Google's documented placeholder instead. It also
# covers calls made by Groq before a mid-answer switch to Gemini.
GEMINI_PLACEHOLDER_SIGNATURE = "skip_thought_signature_validator"


def _gemini_chat_class():
    from langchain_openai import ChatOpenAI

    class GeminiChat(ChatOpenAI):
        def _get_request_payload(self, input_, *, stop=None, **kwargs):
            payload = super()._get_request_payload(input_, stop=stop, **kwargs)
            for message in payload.get("messages", []):
                for call in message.get("tool_calls") or []:
                    call.setdefault("extra_content", {"google": {"thought_signature": GEMINI_PLACEHOLDER_SIGNATURE}})
            return payload

    return GeminiChat


@dataclass
class ModelSet:
    """The primary model, backups that take over if it fails, and a small model for rewrites."""

    primary: object
    backups: list
    names: list[str]
    rewriter: object | None = None

    def plain(self):
        return self.primary.with_fallbacks(self.backups) if self.backups else self.primary

    def with_tools(self, tools):
        bound = self.primary.bind_tools(tools)
        if self.backups:
            bound = bound.with_fallbacks([b.bind_tools(tools) for b in self.backups])
        return bound

    def rewrite_runnable(self):
        return self.rewriter or self.plain()


_cache: dict[tuple, ModelSet] = {}


def get_models(settings: Settings) -> ModelSet | None:
    """Build the models from whichever API keys are set. Returns None when there are none.

    Keys are read on every call (see config.get_secret), so adding a key to .env turns live
    answers on without restarting the app.
    """
    groq_key, google_key = get_secret("GROQ_API_KEY"), get_secret("GOOGLE_API_KEY")
    cache_key = (groq_key, google_key, settings.groq_model, settings.rewrite_model, settings.gemini_model)
    if cache_key in _cache:
        return _cache[cache_key]

    gemini = None
    if google_key:
        gemini = _gemini_chat_class()(
            model=settings.gemini_model,
            api_key=google_key,
            base_url=GEMINI_BASE_URL,
            temperature=0,
            # No retries: on a 429 the client waits out Retry-After (about a minute per call), so a
            # busy backup used to keep the user waiting two minutes just to see "busy, try again"
            max_retries=0,
            timeout=settings.llm_timeout_seconds,
        )

    models, names, rewriter = [], [], None
    if groq_key:
        from langchain_groq import ChatGroq

        def groq(model: str):
            return ChatGroq(
                model=model,
                api_key=groq_key,
                temperature=0,
                reasoning_effort="low",  # gpt-oss models: faster replies, fewer tokens
                max_retries=0 if gemini else 2,  # with a backup, don't wait out rate limits
                request_timeout=settings.llm_timeout_seconds,
            )

        models.append(groq(settings.groq_model))
        names.append(f"Groq · {settings.groq_model}")
        rewriter = groq(settings.rewrite_model)
        if gemini:
            rewriter = rewriter.with_fallbacks([gemini])
    if gemini:
        models.append(gemini)
        names.append(f"Gemini · {settings.gemini_model}")
    if not models:
        return None

    _cache.clear()
    _cache[cache_key] = ModelSet(models[0], models[1:], names, rewriter)
    return _cache[cache_key]


def _status_code(exc: Exception) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        code = getattr(obj, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def describe_error(exc: Exception) -> str:
    """Turn an API exception into a short message a customer can understand."""
    name = type(exc).__name__
    code = _status_code(exc)
    text = str(exc).lower()
    if code == 401 or "authentication" in name.lower() or "invalid api key" in text:
        return "The AI service rejected the API key. The app owner needs to check GROQ_API_KEY."
    if code == 429 or "ratelimit" in name.lower() or "rate limit" in text:
        return "The AI service is busy right now (rate limit). Please try again in a minute."
    if "timeout" in name.lower() or "timed out" in text:
        return "The AI service took too long to reply. Please try again."
    if "connection" in name.lower() or "connect" in text:
        return "Couldn't reach the AI service. Please check the internet connection and try again."
    if code and code >= 500:
        return "The AI service is having problems right now. Please try again shortly."
    if code == 400 and ("context" in text or "too long" in text or "tokens" in text):
        return "The conversation got too long for the AI model. Please start a new chat."
    log.error("Unexpected LLM error: %s: %s", name, exc)
    return f"Something went wrong while writing the answer ({name}). Please try again."
