"""The chat loop: the LLM answers from Wikipedia facts it fetches with tool calls.

Compared with the class version (one LLM call that answers from memory):
- Facts are looked up, not remembered: the model calls get_movie / get_movie_section /
  search_movies, so budgets, box office and release dates come from Wikipedia.
- Every answer ends with links to the Wikipedia pages it used.
- Groq first; if Groq is rate-limited or down, Gemini answers instead.
- Replies in the user's language and script (English, Hindi, Hinglish).
- History is trimmed, odd input is handled, and API errors become friendly messages.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from .config import GEMINI_BASE_URL, GROQ_BASE_URL, Settings, get_secret
from .tools import TOOLS, Source, ToolResult, run_tool, status_line

log = logging.getLogger(__name__)

HEARD_PREFIX = "🎙️ *Heard:* “"  # the app starts replies to voice questions with this
_HEARD = re.compile(r"^🎙️ \*Heard:\* “(.*?)”\s*", re.DOTALL)
_SOURCES_FOOTER = re.compile(r"\n+---\n📚 \*\*Sources:\*\*.*$", re.DOTALL)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_THINK = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)
# Gemini needs a "thought signature" on tool calls it gets back; this is Google's documented
# placeholder for calls it didn't make itself (or whose signature was lost)
GEMINI_PLACEHOLDER_SIGNATURE = "skip_thought_signature_validator"

SYSTEM_PROMPT = """You are "AI Movie", a friendly expert on films from every industry: Bollywood, Hollywood, Tollywood, Kollywood and world cinema. Your tools read English Wikipedia.

Rules:
1. For a question about a specific film, call get_movie first (it includes the main cast and their characters). Then call get_movie_section for anything beyond that: plot → "Plot", the full cast → "Cast", box-office details → "Box office", reviews → "Critical response", awards → "Accolades". Use search_movies when the title is unclear or only described.
2. Every name, role, number and date must come from tool results. If Wikipedia doesn't say, tell the user. Quote money exactly as given (₹ crore, $ million), with no conversions of your own.
3. Verdict (flop / average / hit / super hit / blockbuster): use what the summary or Box office section says; otherwise compare box office with budget and call it a rough estimate.
4. For "tell me about <film>", open with a short Movie Card (Director, Lead cast, Production house, Release date, Running time, Budget, Box office, Verdict). For a specific question, answer just that.
5. If other_matches lists a different film with the same name, say which one you used.
6. Broad questions (recommendations, trivia) may use your own knowledge, but look up any numbers you give.
7. Only discuss movies, actors and the film industry; politely decline anything else. No big spoilers unless asked.
8. Don't list sources or say where a fact came from; the app adds the links. Be concise and use bullets.

Reply language: {language_rule}
Today's date: {today}."""

LANGUAGE_RULES = {
    "hindi": "Hindi in Devanagari script, including headings and labels (the user wrote in Devanagari). Keep film titles and the names of people and characters exactly as Wikipedia writes them, in English letters.",
    "auto": (
        "the same language and script as the user's latest message. Hinglish (Hindi in English letters, e.g. "
        "'Pathaan ka budget kitna tha?') gets a Hinglish reply in English letters, never Devanagari. "
        "Otherwise English, unless they clearly wrote in another language."
    ),
}

NO_KEY_MESSAGE = (
    "⚠️ **The AI isn't set up yet:** no `GROQ_API_KEY` (or `GOOGLE_API_KEY`) is configured. "
    "Owner: add it to `.env`, or as an environment variable on Render."
)


def language_rule(question: str) -> str:
    return LANGUAGE_RULES["hindi" if _DEVANAGARI.search(question or "") else "auto"]


def get_text(content) -> str:
    """Text from a Gradio message: a string, a list of parts, or a file dict (→ '')."""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return " ".join(get_text(part) for part in content).strip()
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text", ""))
        return str(content.get("text", "")) if "text" in content and "path" not in content else ""
    return ""


def clean_answer(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def describe_error(exc: Exception) -> str:
    """A short, friendly reason for an API failure (never the raw error, which can be long)."""
    if isinstance(exc, APIStatusError):
        if exc.status_code in (401, 403):
            return "the API key was rejected (check GROQ_API_KEY)"
        if exc.status_code == 429:
            return "the AI service is busy right now (rate limit). Please try again in a minute"
        if exc.status_code == 413:
            return "the conversation is too long for the AI's limit. Please start a new chat"
        if exc.status_code >= 500:
            return "the AI service is having problems. Please try again shortly"
        return f"the AI service refused the request (HTTP {exc.status_code})"
    if isinstance(exc, APITimeoutError):
        return "the AI service took too long to reply. Please try again"
    if isinstance(exc, APIConnectionError):
        return "the AI service couldn't be reached. Please check the connection and try again"
    return "something went wrong while answering. Please try again"


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError):
        return exc.status_code in (408, 413, 429) or exc.status_code >= 500
    return isinstance(exc, (APIConnectionError, APITimeoutError))


@dataclass
class Provider:
    name: str  # "Groq" / "Gemini"
    model: str
    client: object  # an OpenAI-compatible client

    @property
    def is_gemini(self) -> bool:
        return self.name == "Gemini"


def make_providers(settings: Settings) -> list[Provider]:
    """Groq's main model first, then other Groq models (each has its own rate limit), then
    Gemini. Only providers with a key are used."""
    providers = []
    groq_key, google_key = get_secret("GROQ_API_KEY"), get_secret("GOOGLE_API_KEY")
    if groq_key:
        models = list(dict.fromkeys([settings.groq_model, *settings.groq_backup_models]))
        has_backup = bool(google_key) or len(models) > 1
        groq = OpenAI(
            base_url=GROQ_BASE_URL, api_key=groq_key, timeout=settings.llm_timeout_seconds,
            max_retries=0 if has_backup else 2,  # with a backup waiting, don't sit out a rate limit
        )
        providers.extend(Provider("Groq", model, groq) for model in models)
    if google_key:
        providers.append(Provider("Gemini", settings.gemini_model, OpenAI(
            base_url=GEMINI_BASE_URL, api_key=google_key, timeout=settings.llm_timeout_seconds, max_retries=0,
        )))
    return providers


@dataclass
class Reply:
    """One update for the chat window. The last one has done=True."""

    text: str
    sources: list[Source] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    model: str = ""
    done: bool = False
    error: str | None = None


class _ProviderFailed(Exception):
    def __init__(self, cause: Exception, answered: bool):
        super().__init__(str(cause))
        self.cause, self.answered = cause, answered


def sources_footer(sources: list[Source]) -> str:
    unique: dict[str, Source] = {}
    for s in sources:
        unique.setdefault(s.url, s)
    if not unique:
        return ""
    links = " · ".join(f"[{s.title}]({s.url})" for s in unique.values())
    return f"\n\n---\n📚 **Sources:** {links} (Wikipedia)"


class Assistant:
    def __init__(
        self,
        settings: Settings | None = None,
        providers_fn: Callable[[], list[Provider]] | None = None,
        tool_runner: Callable[[str, dict], ToolResult] | None = None,
    ):
        self.settings = settings or Settings()
        self.providers_fn = providers_fn or (lambda: make_providers(self.settings))
        self.tool_runner = tool_runner or (
            lambda name, args: run_tool(name, args, self.settings.max_tool_result_chars)
        )

    # ---- history -------------------------------------------------------------------------
    def history_messages(self, history) -> list[dict]:
        """Gradio history → OpenAI messages: the last few turns, text only, starting with the user."""
        messages: list[dict] = []
        for item in history or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:  # old [user, bot] pairs
                pairs = [("user", item[0]), ("assistant", item[1])]
            elif isinstance(item, dict):
                pairs = [(item.get("role"), item.get("content"))]
            else:
                continue
            for role, content in pairs:
                if role not in ("user", "assistant"):
                    continue
                text = get_text(content).strip()
                if role == "assistant":
                    heard = _HEARD.match(text)
                    if heard and messages and messages[-1]["role"] == "user" and not messages[-1]["content"]:
                        messages[-1]["content"] = heard.group(1).strip()  # the voice question, as text
                    text = _SOURCES_FOOTER.sub("", _HEARD.sub("", text)).strip()
                messages.append({"role": role, "content": text})

        messages = [m for m in messages if m["content"]]
        merged: list[dict] = []
        for m in messages:  # the API wants user/assistant turns to alternate
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(dict(m))
        merged = merged[-self.settings.max_history_messages:]
        while merged and merged[0]["role"] != "user":
            merged.pop(0)
        limit = self.settings.max_history_chars_per_message
        for m in merged:
            if len(m["content"]) > limit:
                m["content"] = m["content"][:limit] + " …"
        return merged

    # ---- answering -------------------------------------------------------------------------
    def respond(self, message, history=None) -> Iterator[Reply]:
        question = get_text(message).strip()
        if not question:
            yield Reply("Please type a question about a movie, or record one with the mic.", done=True)
            return
        if len(question) > self.settings.max_question_chars:
            yield Reply(
                f"That message is {len(question):,} characters long. Please keep questions under "
                f"{self.settings.max_question_chars:,} characters.",
                done=True,
            )
            return

        providers = self.providers_fn()
        if not providers:
            yield Reply(NO_KEY_MESSAGE, done=True, error="no_api_key")
            return

        system = SYSTEM_PROMPT.format(language_rule=language_rule(question), today=date.today().isoformat())
        base = [{"role": "system", "content": system}, *self.history_messages(history), {"role": "user", "content": question}]

        for i, provider in enumerate(providers):
            try:
                yield from self._answer(provider, base)
                return
            except _ProviderFailed as failed:
                last = i == len(providers) - 1
                if failed.answered or last or not _is_retryable(failed.cause):
                    log.warning("%s failed: %r", provider.name, failed.cause)
                    yield Reply(f"⚠️ Sorry, {describe_error(failed.cause)}.", done=True, error=type(failed.cause).__name__)
                    return
                log.warning("%s failed (%r); switching to %s", provider.name, failed.cause, providers[i + 1].name)

    def _answer(self, provider: Provider, base: list[dict]) -> Iterator[Reply]:
        messages = [dict(m) for m in base]
        sources: list[Source] = []
        tools_used: list[str] = []
        status = ""
        answered = False

        for round_number in range(self.settings.max_tool_rounds + 1):
            allow_tools = round_number < self.settings.max_tool_rounds
            text, calls = "", []
            try:
                for text, calls in self._stream(provider, messages, allow_tools):
                    shown = clean_answer(text)
                    if shown:
                        answered = True
                        yield Reply(shown, sources, tools_used, provider.model)
            except Exception as exc:
                raise _ProviderFailed(exc, answered) from exc

            if not calls:
                answer = clean_answer(text) or (
                    "I couldn't put an answer together. Please try rephrasing, or name the film."
                )
                yield Reply(answer + sources_footer(sources), sources, tools_used, provider.model, done=True)
                return

            messages.append(self._assistant_tool_message(provider, text, calls))
            for call in calls:
                try:
                    args = json.loads(call["arguments"] or "{}")
                    if not isinstance(args, dict):
                        raise ValueError
                except ValueError:
                    args = None
                if args is None:
                    result = ToolResult(json.dumps({"error": "The arguments were not valid JSON."}))
                else:
                    status = f"_{status_line(call['name'], args)}_"
                    yield Reply(status, sources, tools_used, provider.model)
                    result = self.tool_runner(call["name"], args)
                    tools_used.append(f"{call['name']}({', '.join(str(v) for v in args.values())})")
                    sources.extend(result.sources)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result.content})

    def _stream(self, provider: Provider, messages: list[dict], allow_tools: bool):
        """Stream one model call. Yields (text so far, tool calls so far)."""
        kwargs = {"tools": TOOLS, "tool_choice": "auto"} if allow_tools else {}
        if provider.is_gemini or "gpt-oss" in provider.model:  # other models reject this option
            kwargs["reasoning_effort"] = "low"  # a quick answer beats a long think for movie facts
        stream = provider.client.chat.completions.create(
            model=provider.model, messages=messages, stream=True, temperature=0.3, **kwargs,
        )
        text, slots = "", {}
        try:
            for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                if delta.content:
                    text += delta.content
                for tc in delta.tool_calls or []:
                    index = tc.index if tc.index is not None else len(slots)
                    slot = slots.setdefault(index, {"id": None, "name": "", "arguments": "", "extra": None})
                    slot["id"] = tc.id or slot["id"]
                    if tc.function is not None:
                        slot["name"] += tc.function.name or ""
                        slot["arguments"] += tc.function.arguments or ""
                    extra = (getattr(tc, "model_extra", None) or {}).get("extra_content")
                    slot["extra"] = extra or slot["extra"]
                yield text, []
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        calls = []
        for n, (_, slot) in enumerate(sorted(slots.items())):
            if slot["name"]:
                calls.append({**slot, "id": slot["id"] or f"call_{n}"})
        yield text, calls

    @staticmethod
    def _assistant_tool_message(provider: Provider, text: str, calls: list[dict]) -> dict:
        tool_calls = []
        for call in calls:
            entry = {"id": call["id"], "type": "function",
                     "function": {"name": call["name"], "arguments": call["arguments"] or "{}"}}
            if provider.is_gemini:
                entry["extra_content"] = call["extra"] or {"google": {"thought_signature": GEMINI_PLACEHOLDER_SIGNATURE}}
            tool_calls.append(entry)
        return {"role": "assistant", "content": clean_answer(text) or None, "tool_calls": tool_calls}
