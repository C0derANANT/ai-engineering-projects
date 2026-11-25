"""The answer pipeline, with a scripted fake LLM (no API key or network needed)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from rag.assistant import (
    HEARD_PREFIX,
    Assistant,
    clean_answer,
    language_rule,
    parse_citations,
    parse_rewrite,
)
from rag.tools import build_tools

from .conftest import FakeLLM, make_hits, model_set


class RateLimitError(Exception):
    status_code = 429


def make_assistant(settings, store, llm=None, hits=None, search_error=None):
    searched = []

    def search(query, k):
        searched.append(query)
        if search_error:
            raise search_error
        return hits if hits is not None else make_hits(3)

    assistant = Assistant(
        settings=settings,
        search_fn=search,
        tools=build_tools(store),
        models_fn=(lambda: model_set(llm)) if llm else (lambda: None),
        order_ids=store.ids(),
    )
    return assistant, searched


def final(replies):
    replies = list(replies)
    assert replies[-1].done
    return replies[-1]


def test_streams_answer_with_citations(settings, store):
    llm = FakeLLM(["Refunds take 1–3 days for UPI [2]. See also [9]."])
    assistant, searched = make_assistant(settings, store, llm)
    replies = list(assistant.respond("How long do UPI refunds take?"))
    assert replies[0].text.startswith("_Searching")
    assert len([r for r in replies if not r.done]) > 3  # streamed in pieces
    last = replies[-1]
    assert last.cited == {2}  # [9] doesn't exist, so it's ignored
    assert searched == ["test query"]  # the rewritten query was used for search
    assert last.model == "fake-model"


def test_tool_call_round_trip(settings, store):
    llm = FakeLLM([
        [{"name": "cancellation_quote", "args": {"order_id": "1042"}, "id": "call_1"}],
        "You'll get ₹299.79 back for order #1042 [1].",
    ])
    assistant, _ = make_assistant(settings, store, llm)
    replies = list(assistant.respond("Cancel 1042, how much back?"))
    assert any("Working out the cancellation charges #1042" in r.text for r in replies)
    last = replies[-1]
    assert last.tools_used == ["cancellation_quote(1042)"]
    assert "299.79" in last.text
    tool_message = llm.calls[1][-1]
    assert '"refund_total": 299.79' in tool_message.content


def test_tool_calls_without_ids_get_one(settings, store):
    llm = FakeLLM([[{"name": "lookup_order", "args": {"order_id": "1044"}}], "Your order is late."])
    assistant, _ = make_assistant(settings, store, llm)
    assert final(assistant.respond("Where is 1044?")).tools_used == ["lookup_order(1044)"]
    assert llm.calls[1][-1].tool_call_id.startswith("call_")


def test_unknown_tool_and_bad_arguments_dont_crash(settings, store):
    llm = FakeLLM([
        [{"name": "delete_everything", "args": {}, "id": "a"}, {"name": "item_refund_quote", "args": {"items": "x"}, "id": "b"}],
        "Sorry, I couldn't check that.",
    ])
    assistant, _ = make_assistant(settings, store, llm)
    assert final(assistant.respond("refund?")).text == "Sorry, I couldn't check that."
    results = [m.content for m in llm.calls[1][-2:]]
    assert "Unknown tool" in results[0] and "error" in results[1]


def test_endless_tool_calls_stop_after_the_limit(settings, store):
    call = [{"name": "lookup_order", "args": {"order_id": "1042"}, "id": "x"}]
    llm = FakeLLM([call] * settings.max_tool_rounds + ["Here is the answer."])
    assistant, _ = make_assistant(settings, store, llm)
    assert final(assistant.respond("loop")).text == "Here is the answer."
    assert len(llm.calls) == settings.max_tool_rounds + 1


@pytest.mark.parametrize("message", ["", "   ", None])
def test_empty_message(settings, store, message):
    assistant, searched = make_assistant(settings, store, FakeLLM([]))
    assert "type a question" in final(assistant.respond(message)).text
    assert searched == []


def test_too_long_message(settings, store):
    assistant, _ = make_assistant(settings, store, FakeLLM([]))
    assert "characters long" in final(assistant.respond("x" * 5000)).text


def test_without_api_key_it_shows_passages(settings, store):
    assistant, searched = make_assistant(settings, store, llm=None)
    last = final(assistant.respond("What is the platform fee?"))
    assert last.error == "no_api_key" and "GROQ_API_KEY" in last.text
    assert "Passage 1" in last.text and searched == ["What is the platform fee?"]


def test_failed_rewrite_falls_back_to_the_raw_question(settings, store):
    llm = FakeLLM(["Answer."], rewrite=RuntimeError("down"))
    assistant, searched = make_assistant(settings, store, llm)
    final(assistant.respond("platform fee?"))
    assert searched == ["platform fee?"]


def test_search_failure_still_answers(settings, store):
    llm = FakeLLM(["I don't have that information."])
    assistant, _ = make_assistant(settings, store, llm, search_error=RuntimeError("db"))
    last = final(assistant.respond("hi"))
    assert last.hits == [] and "information" in last.text


def test_rate_limit_gives_a_friendly_message(settings, store):
    assistant, _ = make_assistant(settings, store, FakeLLM([RateLimitError("429")]))
    last = final(assistant.respond("refund?"))
    assert "busy" in last.text and last.error


def test_empty_model_output_gets_a_fallback(settings, store):
    assistant, _ = make_assistant(settings, store, FakeLLM(["<think>hmm</think>"]))
    assert "rephrasing" in final(assistant.respond("??")).text


# ---- history -------------------------------------------------------------------------------
def test_history_formats_and_limits(settings, store):
    assistant, _ = make_assistant(settings, store, FakeLLM([]))
    history = [
        {"role": "assistant", "content": "Welcome!"},  # dropped: history must start with the user
        {"role": "user", "content": "cancel 1042?"},
        {"role": "assistant", "content": [{"type": "text", "text": "₹299.79"}]},
        {"role": "user", "content": {"path": "/tmp/a.wav", "mime_type": "audio/wav"}},  # file only
        {"role": "assistant", "content": f"{HEARD_PREFIX}what about 1043?”\n\nNothing back."},
        ["old style question", "old style answer"],
    ]
    messages = assistant.history_messages(history)
    assert [type(m).__name__ for m in messages] == [
        "HumanMessage", "AIMessage", "HumanMessage", "AIMessage", "HumanMessage", "AIMessage"
    ]
    assert messages[2].content == "what about 1043?"  # recovered from the voice reply
    assert messages[3].content == "Nothing back."

    long_history = [{"role": r, "content": "y" * 5000} for r in ["user", "assistant"] * 10]
    trimmed = assistant.history_messages(long_history)
    assert len(trimmed) <= settings.max_history_messages
    assert all(len(m.content) <= settings.max_history_chars_per_message + 2 for m in trimmed)
    assert isinstance(trimmed[0], HumanMessage)


def test_follow_up_sends_history_to_the_model(settings, store):
    llm = FakeLLM(["Stage D means no refund."])
    assistant, _ = make_assistant(settings, store, llm)
    history = [{"role": "user", "content": "cancel 1042?"}, {"role": "assistant", "content": "₹299.79 back."}]
    final(assistant.respond("what if it was cooking?", history))
    sent = llm.calls[0]
    assert isinstance(sent[1], HumanMessage) and isinstance(sent[2], AIMessage)
    assert sent[-1].content == "what if it was cooking?"


# ---- helpers -------------------------------------------------------------------------------
def test_language_rule():
    assert "Devanagari script." in language_rule("मेरा ऑर्डर कहाँ है?", "English")
    assert "Do NOT use Devanagari" in language_rule("mera order kahan hai", "Hinglish")
    assert "Do NOT use Devanagari" in language_rule("mera order kahan hai", "Hindi")
    assert language_rule("where is my order", None) == "English."
    assert language_rule("¿dónde está mi pedido?", "Spanish").startswith("Spanish")


def test_parse_rewrite_handles_markdown():
    assert parse_rewrite("**Language:** Hinglish\n**Query:** \"refund for missing item\"") == (
        "Hinglish", "refund for missing item"
    )
    assert parse_rewrite("just some text") == (None, None)


def test_clean_answer_and_citations():
    assert clean_answer("<think>plan</think>Answer 【3†source】 and [1]") == "Answer [3] and [1]"
    assert clean_answer("<think>unfinished") == ""
    assert parse_citations("a [1] b [2, 3] c [4–5] d [99]", 5) == {1, 2, 3, 4, 5}
