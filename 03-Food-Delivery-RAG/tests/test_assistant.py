"""The RAG pipeline, with a scripted fake LLM (no API key or network needed)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from rag.assistant import Assistant, clean_answer, describe_error, language_rule, parse_citations, parse_rewrite

from .conftest import FakeLLM, fake_models, make_hits


class RateLimitError(Exception):
    status_code = 429


def make_assistant(settings, llm=None, hits=None, search_error=None):
    searched = []

    def search(query, k):
        searched.append(query)
        if search_error:
            raise search_error
        return hits if hits is not None else make_hits(3)

    assistant = Assistant(
        settings=settings,
        search_fn=search,
        models_fn=(lambda: fake_models(llm)) if llm else (lambda: None),
    )
    return assistant, searched


def final(replies):
    replies = list(replies)
    assert replies[-1].done
    return replies[-1]


def test_streams_answer_with_citations(settings):
    llm = FakeLLM(["Refunds take 1–3 days for UPI [2]. See also [9]."])
    assistant, searched = make_assistant(settings, llm)
    replies = list(assistant.respond("How long do UPI refunds take?"))
    assert replies[0].text.startswith("_Searching")
    assert len([r for r in replies if not r.done]) > 3  # streamed in pieces
    last = replies[-1]
    assert last.text == "Refunds take 1–3 days for UPI [2]. See also [9]."
    assert last.cited == {2}  # [9] doesn't exist, so it's ignored
    assert searched == ["test query"]  # the rewritten query was used for search
    assert last.model == "Fake" and last.query == "test query"


def test_passages_go_into_the_system_prompt(settings):
    llm = FakeLLM(["ok"])
    assistant, _ = make_assistant(settings, llm)
    final(assistant.respond("refund?"))
    system = llm.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert "[1] Source: policies/doc1.md › Section 1" in system.content and "Passage 3 about refunds." in system.content


def test_no_passages_found(settings):
    llm = FakeLLM(["I don't have that information."])
    assistant, _ = make_assistant(settings, llm, hits=[])
    last = final(assistant.respond("Who is the CEO's dog?"))
    assert "No passages were found" in llm.calls[0][0].content and last.cited == set()


@pytest.mark.parametrize("message", ["", "   ", None, [{"type": "text", "text": " "}]])
def test_empty_message(settings, message):
    assistant, searched = make_assistant(settings, FakeLLM([]))
    assert "type a question" in final(assistant.respond(message)).text
    assert searched == []


def test_message_as_a_list_of_parts(settings):
    assistant, _ = make_assistant(settings, FakeLLM(["ok"]))
    assert final(assistant.respond([{"type": "text", "text": "platform fee?"}])).text == "ok"


def test_too_long_message(settings):
    assistant, _ = make_assistant(settings, FakeLLM([]))
    assert "characters long" in final(assistant.respond("x" * 5000)).text


def test_without_api_key_it_shows_passages(settings):
    assistant, searched = make_assistant(settings, llm=None)
    last = final(assistant.respond("What is the platform fee?"))
    assert last.error == "no_api_key" and "GROQ_API_KEY" in last.text
    assert "Passage 1" in last.text and searched == ["What is the platform fee?"]


def test_without_api_key_and_a_broken_db(settings):
    assistant, _ = make_assistant(settings, llm=None, search_error=RuntimeError("db"))
    assert "couldn't be searched" in final(assistant.respond("fee?")).text


def test_failed_rewrite_falls_back_to_the_raw_question(settings):
    llm = FakeLLM(["Answer."], rewrite=RuntimeError("down"))
    assistant, searched = make_assistant(settings, llm)
    final(assistant.respond("platform fee?"))
    assert searched == ["platform fee?"]


@pytest.mark.parametrize("rewrite", ["no idea", "language: English\nquery: x"])
def test_unusable_rewrite_falls_back_to_the_raw_question(settings, rewrite):
    assistant, searched = make_assistant(settings, FakeLLM(["ok"], rewrite=rewrite))
    final(assistant.respond("platform fee?"))
    assert searched == ["platform fee?"]


def test_search_failure_still_answers(settings):
    llm = FakeLLM(["I don't have that information."])
    assistant, _ = make_assistant(settings, llm, search_error=RuntimeError("db"))
    last = final(assistant.respond("hi"))
    assert last.hits == [] and "information" in last.text


def test_rate_limit_gives_a_friendly_message(settings):
    assistant, _ = make_assistant(settings, FakeLLM([RateLimitError("429")]))
    last = final(assistant.respond("refund?"))
    assert "busy" in last.text and last.error


def test_error_mid_answer_keeps_the_partial_text(settings):
    class Broken(FakeLLM):
        def stream(self, messages):
            yield from super().stream(messages)
            raise TimeoutError("timed out")

    assistant, _ = make_assistant(settings, Broken(["UPI refunds take 1–3 days [1]."]))
    last = final(assistant.respond("refund time?"))
    assert last.text.startswith("UPI refunds take 1–3 days [1].") and "may be incomplete" in last.text
    assert last.cited == {1}


def test_empty_model_output_gets_a_fallback(settings):
    assistant, _ = make_assistant(settings, FakeLLM(["<think>hmm</think>"]))
    assert "rephrasing" in final(assistant.respond("??")).text


# ---- history and language ------------------------------------------------------------------
def test_history_formats_and_limits(settings):
    assistant, _ = make_assistant(settings, FakeLLM([]))
    history = [
        {"role": "assistant", "content": "Welcome!"},  # dropped: history must start with the user
        {"role": "user", "content": "can I cancel?"},
        {"role": "assistant", "content": [{"type": "text", "text": "Yes, within 60 seconds."}]},
        {"role": "user", "content": {"path": "/tmp/a.png", "mime_type": "image/png"}},  # a file: skipped
        {"role": "user", "content": "and after that?"},
        {"role": "user", "content": "while cooking?"},  # two user turns in a row get merged
        {"role": "assistant", "content": "A 100% fee."},
        ["old style question", "old style answer"],
    ]
    messages = assistant.history_messages(history)
    assert [type(m).__name__ for m in messages] == [
        "HumanMessage", "AIMessage", "HumanMessage", "AIMessage", "HumanMessage", "AIMessage"
    ]
    assert messages[2].content == "and after that?\nwhile cooking?"

    long_history = [{"role": r, "content": "y" * 5000} for r in ["user", "assistant"] * 10]
    trimmed = assistant.history_messages(long_history)
    assert len(trimmed) <= settings.max_history_messages
    assert all(len(m.content) <= settings.max_history_chars_per_message + 2 for m in trimmed)
    assert isinstance(trimmed[0], HumanMessage)


def test_follow_up_sends_history_to_the_model(settings):
    llm = FakeLLM(["A 100% fee [1]."])
    assistant, _ = make_assistant(settings, llm)
    history = [{"role": "user", "content": "Can I cancel?"}, {"role": "assistant", "content": "Yes, free in 60 s."}]
    final(assistant.respond("what if it was cooking?", history))
    sent = llm.calls[0]
    assert isinstance(sent[1], HumanMessage) and isinstance(sent[2], AIMessage)
    assert sent[-1].content == "what if it was cooking?"


@pytest.mark.parametrize("question, label, expected", [
    ("मेरा रिफंड कब आएगा?", "English", "Devanagari script."),
    ("mera refund kab aayega", "Hinglish", "Do NOT use Devanagari"),
    ("mera refund kab aayega", "Hindi", "Do NOT use Devanagari"),  # Hindi in English letters
])
def test_reply_language_follows_the_question(settings, question, label, expected):
    llm = FakeLLM(["ok"], rewrite=f"language: {label}\nquery: refund time")
    assistant, _ = make_assistant(settings, llm)
    final(assistant.respond(question))
    assert expected in llm.calls[0][0].content


def test_language_rule():
    assert language_rule("where is my order", None) == "English."
    assert language_rule("¿dónde está mi pedido?", "Spanish").startswith("Spanish")


# ---- helpers -------------------------------------------------------------------------------
def test_parse_rewrite_handles_markdown():
    assert parse_rewrite("**Language:** Hinglish\n**Query:** \"refund for missing item\"") == (
        "Hinglish", "refund for missing item"
    )
    assert parse_rewrite("just some text") == (None, None)


def test_clean_answer_and_citations():
    assert clean_answer("<think>plan</think>Answer 【3†source】 and [1]") == "Answer [3] and [1]"
    assert clean_answer("<think>unfinished") == ""
    assert parse_citations("a [1] b [2, 3] c [4–5] d [99]", 5) == {1, 2, 3, 4, 5}


@pytest.mark.parametrize("status, words", [
    (401, "API key"), (429, "busy"), (500, "having problems"), (418, "went wrong"),
])
def test_describe_error(status, words):
    error = type("APIError", (Exception,), {"status_code": status})("x")
    assert words in describe_error(error)
