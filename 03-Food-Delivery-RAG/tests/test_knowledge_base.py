import dataclasses
import logging
import shutil

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from rag.knowledge_base import (
    BGE_QUERY_INSTRUCTION,
    FastEmbedEmbeddings,
    chunk_header,
    load_documents,
    make_embeddings,
    open_vector_store,
    search,
    split_documents,
    strip_chunk_header,
)

from .conftest import KB_DIR

FAKE_EMBEDDINGS = DeterministicFakeEmbedding(size=32)


def test_loads_every_document_with_its_doc_type():
    docs = load_documents(KB_DIR)
    assert len(docs) == 18
    assert {d.metadata["doc_type"] for d in docs} == {
        "company", "customer-faqs", "ordering", "policies", "support", "hr-policies"
    }
    assert all(d.metadata["title"] for d in docs)


def test_loose_empty_and_binary_files_are_skipped(tmp_path, caplog):
    kb = tmp_path / "kb"
    shutil.copytree(KB_DIR / "policies", kb / "policies")
    (kb / "README.md").write_text("# loose file", encoding="utf-8")  # breaks the class notebook's loader
    (kb / "policies" / "empty.md").write_text("   ", encoding="utf-8")
    (kb / "policies" / "binary.md").write_bytes(b"\xff\xfe\x00bad")
    with caplog.at_level(logging.WARNING):
        docs = load_documents(kb)
    assert len(docs) == 2
    assert "README.md" in caplog.text and "empty" in caplog.text and "UTF-8" in caplog.text


def test_missing_or_empty_knowledge_base(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_documents(tmp_path / "nope")
    (tmp_path / "kb" / "x").mkdir(parents=True)
    with pytest.raises(ValueError):
        load_documents(tmp_path / "kb")


def test_chunks_follow_headings_and_carry_labels():
    chunks = split_documents(load_documents(KB_DIR), chunk_size=1000, chunk_overlap=150)
    assert len(chunks) > 250
    for c in chunks:
        assert c.page_content.startswith(chunk_header(c.metadata["title"], c.metadata["section"]))
        body = strip_chunk_header(c.page_content)
        assert len(body) <= 1000
        assert any(not line.startswith("#") and line.strip() for line in body.splitlines())
    sections = {c.metadata["section"] for c in chunks if c.metadata["source"] == "policies/refund-policy.md"}
    assert "5. How the refund amount is calculated › 5.1 Item-level refunds" in sections


def test_vector_store_builds_once_then_reuses_and_refreshes(settings, tmp_path):
    kb = tmp_path / "kb"
    shutil.copytree(KB_DIR / "company", kb / "company")
    settings = dataclasses.replace(settings, knowledge_base_dir=kb)

    store, info = open_vector_store(settings, embeddings=FAKE_EMBEDDINGS)
    assert info.rebuilt and info.chunks > 0 and info.files == 2

    _, again = open_vector_store(settings, embeddings=FAKE_EMBEDDINGS)
    assert not again.rebuilt and again.chunks == info.chunks

    (kb / "company" / "new.md").write_text("# New doc\n\n## Section\n\n" + "Fresh policy text. " * 20, encoding="utf-8")
    store, changed = open_vector_store(settings, embeddings=FAKE_EMBEDDINGS)
    assert changed.rebuilt and changed.files == 3

    hits = search(store, "late night fee", 3)
    assert [h.number for h in hits] == [1, 2, 3]
    assert all(0 <= h.score <= 1 and not h.text.startswith("[") for h in hits)


class StubTextEmbedding:
    """Stands in for fastembed.TextEmbedding so the test needs no model download."""

    def __init__(self):
        self.batches = []

    def embed(self, texts, batch_size=8):
        self.batches.append(texts)
        return iter([[3.0, 4.0], [0.0, 0.0]][: len(texts)])


def test_fastembed_wrapper_returns_unit_vectors():
    stub = StubTextEmbedding()
    embeddings = FastEmbedEmbeddings("BAAI/bge-small-en-v1.5", model=stub)
    assert embeddings.embed_documents(["a", "b"]) == [[0.6, 0.8], [0.0, 0.0]]  # zero vector left alone
    assert embeddings.embed_query("a") == [0.6, 0.8]
    assert embeddings.embed_documents([]) == [] and len(stub.batches) == 2


def test_bge_queries_get_the_search_instruction(settings, monkeypatch):
    import fastembed

    monkeypatch.setattr(fastembed, "TextEmbedding", lambda **kwargs: StubTextEmbedding())
    bge = make_embeddings(settings)
    bge.embed_query("late night fee")
    bge.embed_documents(["a passage"])
    assert bge._model.batches == [[BGE_QUERY_INSTRUCTION + "late night fee"], ["a passage"]]  # queries only
    other = make_embeddings(dataclasses.replace(settings, embedding_model="sentence-transformers/all-MiniLM-L6-v2"))
    assert other.query_prefix == ""


def test_changing_the_embedding_model_rebuilds(settings, tmp_path):
    kb = tmp_path / "kb"
    shutil.copytree(KB_DIR / "company", kb / "company")
    settings = dataclasses.replace(settings, knowledge_base_dir=kb)
    open_vector_store(settings, embeddings=FAKE_EMBEDDINGS)
    other = dataclasses.replace(settings, embedding_model="sentence-transformers/all-MiniLM-L6-v2")
    assert open_vector_store(other, embeddings=FAKE_EMBEDDINGS)[1].rebuilt
