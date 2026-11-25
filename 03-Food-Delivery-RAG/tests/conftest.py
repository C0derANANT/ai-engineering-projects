"""Shared test fixtures. Tests never use the internet, an API key or a real embedding model."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from rag.config import Settings  # noqa: E402
from rag.knowledge_base import Hit  # noqa: E402
from rag.llm import ModelSet  # noqa: E402
from rag.orders import OrderStore  # noqa: E402

ORDERS_FILE = PROJECT_DIR / "data" / "sample_orders.json"
KB_DIR = PROJECT_DIR / "knowledge-base"


@pytest.fixture(scope="session")
def store() -> OrderStore:
    return OrderStore.from_file(ORDERS_FILE)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(knowledge_base_dir=KB_DIR, vector_db_dir=tmp_path / "vector_db", orders_file=ORDERS_FILE)


def make_hits(n: int = 3) -> list[Hit]:
    return [
        Hit(
            number=i,
            text=f"Passage {i} about refunds.",
            doc_type="policies",
            source=f"policies/doc{i}.md",
            title=f"Doc {i}",
            section=f"Section {i}",
            score=0.8,
        )
        for i in range(1, n + 1)
    ]


class FakeLLM:
    """A scripted chat model: each call returns the next response.

    A response is a string (streamed word by word), a list of tool calls, or an Exception to raise.
    """

    def __init__(self, responses, rewrite="language: English\nquery: test query"):
        self.responses = list(responses)
        self.rewrite = rewrite
        self.calls: list[list] = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def with_fallbacks(self, _):
        return self

    def invoke(self, messages):  # used for the query rewrite
        if isinstance(self.rewrite, Exception):
            raise self.rewrite
        return AIMessage(content=self.rewrite)

    def stream(self, messages) -> Iterator[AIMessageChunk]:
        self.calls.append(list(messages))
        response = self.responses.pop(0) if self.responses else "Done."
        if isinstance(response, Exception):
            raise response
        if isinstance(response, list):  # tool calls
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": c["name"], "args": __import__("json").dumps(c["args"]), "id": c.get("id"), "index": i}
                    for i, c in enumerate(response)
                ],
                response_metadata={"model_name": "fake-model"},
            )
            return
        words = response.split(" ")
        for i, word in enumerate(words):
            yield AIMessageChunk(content=word + (" " if i < len(words) - 1 else ""))
        yield AIMessageChunk(content="", response_metadata={"model_name": "fake-model"})


def model_set(llm: FakeLLM) -> ModelSet:
    return ModelSet(primary=llm, backups=[], names=["Fake"], rewriter=llm)
