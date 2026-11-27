"""The Sources panel and hosting helpers."""

import pytest

from rag.assistant import Reply
from rag.config import server_options
from rag.ui import EMPTY_SOURCES, EXAMPLES, sources_markdown

from .conftest import make_hits


def test_sources_panel():
    assert sources_markdown(None) == EMPTY_SOURCES
    reply = Reply(text="UPI refunds take 1–3 days [2].", hits=make_hits(3), cited={2},
                  query="refund time", model="fake", done=True)
    panel = sources_markdown(reply)
    cited_part, others = panel.split("Also retrieved")
    assert "[2]** ✅" in cited_part and "[1]**" in others and "[3]**" in others
    assert "refund time" in panel and "fake" in panel


def test_sources_panel_before_citations_arrive():
    panel = sources_markdown(Reply(text="Looking…", hits=make_hits(2)))
    assert "Retrieved passages" in panel and "Cited" not in panel
    assert sources_markdown(Reply(text="No key", hits=[])) == EMPTY_SOURCES


def test_examples_are_questions():
    assert len(EXAMPLES) >= 4 and all(e.strip() for e in EXAMPLES)


# ---- hosting -------------------------------------------------------------------------------
def test_listens_on_render_port():
    assert server_options({"PORT": "10000"}) == {"server_name": "0.0.0.0", "server_port": 10000}


@pytest.mark.parametrize("environ", [{}, {"PORT": ""}, {"PORT": "abc"}, {"PORT": "0"}, {"PORT": "70000"}])
def test_keeps_gradio_defaults_without_a_valid_port(environ):
    assert server_options(environ) == {}
