"""The chat loop, with a scripted fake LLM and the fake Wikipedia (no network, no key)."""

import httpx
import openai
import pytest

from movie import assistant as assistant_module
from movie.assistant import (
    GEMINI_PLACEHOLDER_SIGNATURE,
    HEARD_PREFIX,
    NO_KEY_MESSAGE,
    Assistant,
    Provider,
    clean_answer,
    language_rule,
    make_providers,
)
from movie.config import Settings

from .conftest import FakeLLMClient


def api_error(status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.test/chat"))
    return openai.APIStatusError(f"HTTP {status}", response=response, body=None)


def make(replies, backup_replies=None, settings=None):
    """An Assistant on Groq (+ Gemini backup if backup_replies is given)."""
    groq = FakeLLMClient(replies)
    providers = [Provider("Groq", "openai/gpt-oss-120b", groq)]
    gemini = None
    if backup_replies is not None:
        gemini = FakeLLMClient(backup_replies)
        providers.append(Provider("Gemini", "gemini-test", gemini))
    return Assistant(settings or Settings(), providers_fn=lambda: providers), groq, gemini


def final(replies):
    replies = list(replies)
    assert replies[-1].done
    return replies[-1]


GET_MOVIE = [{"name": "get_movie", "arguments": '{"title": "Rocket Raja"}', "id": "call_1"}]


def test_answer_from_wikipedia_with_sources(fake_wiki):
    bot, groq, _ = make([GET_MOVIE, "Rocket Raja was made for ₹100 crore."])
    replies = list(bot.respond("Rocket Raja ka budget?"))
    assert any("Looking up *Rocket Raja*" in r.text for r in replies)  # status while the tool runs
    last = replies[-1]
    assert last.text.startswith("Rocket Raja was made for ₹100 crore.")
    assert "📚 **Sources:** [Rocket Raja (film)](https://en.wikipedia.org/wiki/Rocket_Raja_(film))" in last.text
    assert last.tools_used == ["get_movie(Rocket Raja)"]
    tool_message = groq.calls[1]["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call_1"
    assert "₹100 crore" in tool_message["content"]  # the model saw Wikipedia's numbers
    assert groq.calls[0]["tools"] and groq.calls[0]["reasoning_effort"] == "low"


def test_answers_stream_in_pieces(fake_wiki):
    bot, _, _ = make(["Inception is a 2010 film by Christopher Nolan."])
    replies = list(bot.respond("Who made Inception?"))
    assert len([r for r in replies if not r.done]) > 3
    assert "Sources" not in replies[-1].text  # no tool used, no sources


def test_tool_calls_without_ids_and_bad_arguments(fake_wiki):
    bot, groq, _ = make([[{"name": "get_movie", "arguments": "{not json"}], "Sorry, try again."])
    assert final(bot.respond("budget?")).text == "Sorry, try again."
    tool_message = groq.calls[1]["messages"][-1]
    assert tool_message["tool_call_id"] == "call_0" and "not valid JSON" in tool_message["content"]


def test_endless_tool_calls_stop(fake_wiki):
    settings = Settings()
    bot, groq, _ = make([GET_MOVIE] * settings.max_tool_rounds + ["Here you go."], settings=settings)
    assert final(bot.respond("loop")).text.startswith("Here you go.")
    assert len(groq.calls) == settings.max_tool_rounds + 1
    assert "tools" not in groq.calls[-1]  # the last call can only answer


def test_busy_groq_hands_over_to_gemini_with_a_signature(fake_wiki):
    bot, groq, gemini = make([api_error(429)], [GET_MOVIE, "It made ₹350 crore."])
    last = final(bot.respond("Rocket Raja box office?"))
    assert last.text.startswith("It made ₹350 crore.") and last.model == "gemini-test"
    assistant_turn = gemini.calls[1]["messages"][-2]
    assert assistant_turn["tool_calls"][0]["extra_content"] == {
        "google": {"thought_signature": GEMINI_PLACEHOLDER_SIGNATURE}
    }


def test_gemini_keeps_its_own_signature(fake_wiki):
    call = [{**GET_MOVIE[0], "extra": {"google": {"thought_signature": "real-signature"}}}]
    bot, _, gemini = make([api_error(503)], [call, "Done."])
    final(bot.respond("Rocket Raja?"))
    assert gemini.calls[1]["messages"][-2]["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "real-signature"


def test_groq_tool_calls_have_no_gemini_fields(fake_wiki):
    bot, groq, _ = make([GET_MOVIE, "ok"])
    final(bot.respond("Rocket Raja?"))
    assert "extra_content" not in groq.calls[1]["messages"][-2]["tool_calls"][0]


def test_a_wrong_key_is_not_hidden_by_the_backup(fake_wiki):
    bot, _, gemini = make([api_error(401)], ["never used"])
    last = final(bot.respond("hi"))
    assert "API key was rejected" in last.text and gemini.calls == []


def test_everyone_busy_gives_a_friendly_message(fake_wiki):
    bot, _, _ = make([api_error(429)], [api_error(429)])
    last = final(bot.respond("hi"))
    assert "busy right now" in last.text and last.error


def test_no_switch_after_the_answer_started(fake_wiki):
    class Broken:
        def __iter__(self):
            from types import SimpleNamespace as NS
            yield NS(choices=[NS(delta=NS(content="Half an ", tool_calls=None))])
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.test"))

    bot, groq, gemini = make([], ["never used"])
    groq.chat.completions.create = lambda **kwargs: Broken()
    assert "couldn't be reached" in final(bot.respond("hi")).text
    assert gemini.calls == []


def test_without_a_key(monkeypatch):
    monkeypatch.setattr(assistant_module, "get_secret", lambda name: None)
    last = final(Assistant(Settings()).respond("Who directed Sholay?"))
    assert last.text == NO_KEY_MESSAGE and last.error == "no_api_key"


def test_providers_order(monkeypatch):
    monkeypatch.setattr(assistant_module, "get_secret", lambda name: "key")
    providers = make_providers(Settings())
    assert [(p.name, p.model) for p in providers] == [
        ("Groq", "openai/gpt-oss-120b"), ("Groq", "openai/gpt-oss-20b"), ("Groq", "qwen/qwen3.8-27b"),
        ("Gemini", "gemini-3.6-flash"),
    ]


@pytest.mark.parametrize("message", ["", "   ", None, {"path": "/tmp/a.wav"}])
def test_empty_message(message):
    bot, groq, _ = make([])
    assert "Please type a question" in final(bot.respond(message)).text and groq.calls == []


def test_too_long_message():
    bot, _, _ = make([])
    assert "characters long" in final(bot.respond("x" * 5000)).text


def test_reasoning_option_only_for_models_that_take_it(fake_wiki):
    client = FakeLLMClient(["ok"])
    bot = Assistant(Settings(), providers_fn=lambda: [Provider("Groq", "llama-3.3-70b-versatile", client)])
    final(bot.respond("hi"))
    assert "reasoning_effort" not in client.calls[0]


# ---- history and language -------------------------------------------------------------------
def test_history_is_cleaned_and_trimmed():
    bot, _, _ = make([])
    history = [
        {"role": "assistant", "content": "Welcome!"},  # dropped: history starts with the user
        {"role": "user", "content": "Pathaan budget?"},
        {"role": "assistant", "content": "₹250 crore.\n\n---\n📚 **Sources:** [Pathaan (film)](https://x) (Wikipedia)"},
        {"role": "user", "content": {"path": "/tmp/q.wav", "mime_type": "audio/wav"}},  # a voice question
        {"role": "assistant", "content": f"{HEARD_PREFIX}aur box office?”\n\n₹1,050 crore."},
        {"role": "user", "content": [{"type": "text", "text": "and Jawan?"}]},
        {"role": "user", "content": "its director?"},  # two user turns in a row get merged
    ]
    messages = bot.history_messages(history)
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant", "user"]
    assert messages[1]["content"] == "₹250 crore."  # sources footer removed
    assert messages[2]["content"] == "aur box office?"  # recovered from the voice reply
    assert messages[3]["content"] == "₹1,050 crore."
    assert messages[4]["content"] == "and Jawan?\nits director?"

    long = [{"role": r, "content": "y" * 4000} for r in ["user", "assistant"] * 10]
    trimmed = bot.history_messages(long)
    assert len(trimmed) <= Settings().max_history_messages and trimmed[0]["role"] == "user"
    assert all(len(m["content"]) <= Settings().max_history_chars_per_message + 2 for m in trimmed)


def test_follow_ups_send_the_history(fake_wiki):
    bot, groq, _ = make(["₹250 crore."])
    final(bot.respond("aur budget?", [{"role": "user", "content": "Pathaan?"}, {"role": "assistant", "content": "A 2023 film."}]))
    roles = [m["role"] for m in groq.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_language_rules():
    assert "Devanagari script" in language_rule("बाहुबली 2 का बजट?")
    assert "never Devanagari" in language_rule("Pathaan ka budget kitna tha?")


def test_system_prompt_gets_the_language_rule(fake_wiki):
    bot, groq, _ = make(["ठीक है"])
    final(bot.respond("शोले का निर्देशक कौन था?"))
    assert "Hindi in Devanagari" in groq.calls[0]["messages"][0]["content"]


def test_clean_answer():
    assert clean_answer("<think>plan</think>Answer") == "Answer"
    assert clean_answer("<think>unfinished") == ""


def test_empty_model_output_gets_a_fallback(fake_wiki):
    bot, _, _ = make(["<think>hmm</think>"])
    assert "rephrasing" in final(bot.respond("??")).text
