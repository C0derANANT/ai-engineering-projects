"""Builds and opens the RAG_DB: the Chroma vector database made from knowledge-base/.

Improvements over the class RAG_DB notebook:
- Heading-aware chunks: Markdown is split at #, ## and ### headings first, so a chunk never
  mixes two policies, and each chunk is labelled with its document and section. Those labels
  power the citations in the app.
- Better, lighter embeddings: BAAI/bge-small-en-v1.5 (better at retrieval than the class's
  all-MiniLM-L6-v2), run with ONNX (fastembed) instead of PyTorch, so it fits a 512 MB server.
- Self-refreshing: a fingerprint of the files and settings is stored next to the database.
  If a document changes, the database is rebuilt automatically; otherwise it loads instantly.
- Safe loading: loose files at the top of knowledge-base/, empty files and non-UTF-8 files
  are skipped with a warning instead of crashing the loader.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from .config import Settings

log = logging.getLogger(__name__)

CHUNKER_VERSION = "2"  # bump when the chunking logic changes, to force a rebuild
EMBEDDING_BACKEND = "fastembed-onnx"  # part of the fingerprint: vectors from another backend don't mix
# Texts embedded at once. 32 doubles peak memory (~800 MB measured) for little speed gain; 8 stays near 430 MB.
EMBED_BATCH_SIZE = 8
MANIFEST_NAME = "rag_manifest.json"
HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


# -----------------------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------------------
def _title_of(text: str, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").title()


def load_documents(kb_dir: Path) -> list[Document]:
    """Load knowledge-base/<doc_type>/**/*.md, tagging each file with its folder as doc_type."""
    kb_dir = Path(kb_dir)
    if not kb_dir.is_dir():
        raise FileNotFoundError(f"Knowledge base folder not found: {kb_dir}")

    for loose in sorted(p for p in kb_dir.iterdir() if p.is_file() and not p.name.startswith(".")):
        log.warning("Ignoring %s: put documents inside a doc_type folder, e.g. knowledge-base/policies/", loose.name)

    docs = []
    for folder in sorted(p for p in kb_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        for path in sorted(folder.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                log.warning("Skipping %s: not UTF-8 text", path)
                continue
            if not text.strip():
                log.warning("Skipping %s: file is empty", path)
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "doc_type": folder.name,
                        "source": path.relative_to(kb_dir).as_posix(),
                        "title": _title_of(text, path),
                    },
                )
            )
    if not docs:
        raise ValueError(f"No Markdown documents found in {kb_dir}/<folder>/*.md")
    return docs


# -----------------------------------------------------------------------------------------
# Chunking
# -----------------------------------------------------------------------------------------
def chunk_header(title: str, section: str) -> str:
    return f"[{title} | {section}]\n"


def strip_chunk_header(text: str) -> str:
    """Remove the '[Title | Section]' line added for retrieval, for display."""
    if text.startswith("[") and "]\n" in text[:300]:
        return text.split("]\n", 1)[1]
    return text


def split_documents(docs: list[Document], chunk_size: int = 1000, chunk_overlap: int = 150) -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS, strip_headers=False)
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[Document] = []
    for doc in docs:
        for section in header_splitter.split_text(doc.page_content):
            path = [section.metadata[k] for k in ("h2", "h3") if section.metadata.get(k)]
            section_name = " › ".join(path) or "Introduction"
            for piece in char_splitter.split_text(section.page_content):
                body = "\n".join(line for line in piece.splitlines() if not line.lstrip().startswith("#")).strip()
                if len(body) < 40:  # a heading with no text under it
                    continue
                chunks.append(
                    Document(
                        page_content=chunk_header(doc.metadata["title"], section_name) + piece,
                        metadata={**doc.metadata, "section": section_name, "chunk": len(chunks)},
                    )
                )
    return chunks


# -----------------------------------------------------------------------------------------
# Vector database
# -----------------------------------------------------------------------------------------
def fingerprint(kb_dir: Path, settings: Settings) -> str:
    h = hashlib.sha256()
    h.update(
        f"{CHUNKER_VERSION}|{EMBEDDING_BACKEND}|{settings.embedding_model}|"
        f"{settings.chunk_size}|{settings.chunk_overlap}".encode()
    )
    for path in sorted(Path(kb_dir).rglob("*.md")):
        h.update(path.relative_to(kb_dir).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


class FastEmbedEmbeddings(Embeddings):
    """LangChain embeddings backed by fastembed (ONNX Runtime, no PyTorch).

    Vectors are scaled to length 1, so Chroma's cosine scores stay between 0 and 1.
    """

    def __init__(self, model_name: str, cache_dir: Path | None = None, threads: int | None = None, model=None):
        if model is None:
            from fastembed import TextEmbedding

            model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir) if cache_dir else None, threads=threads)
        self.model_name = model_name
        self._model = model

    @staticmethod
    def _unit(vector) -> list[float]:
        values = [float(x) for x in vector]
        norm = sum(x * x for x in values) ** 0.5
        return [x / norm for x in values] if norm else values

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._unit(v) for v in self._model.embed(list(texts), batch_size=EMBED_BATCH_SIZE)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def make_embeddings(settings: Settings) -> FastEmbedEmbeddings:
    """BGE embeddings via fastembed (the model is downloaded once, then cached)."""
    settings.embedding_cache_dir.mkdir(parents=True, exist_ok=True)
    return FastEmbedEmbeddings(settings.embedding_model, settings.embedding_cache_dir, settings.embedding_threads)


@dataclass
class BuildInfo:
    rebuilt: bool
    chunks: int
    files: int
    seconds: float


def open_vector_store(settings: Settings, embeddings=None, force_rebuild: bool = False):
    """Return (vectorstore, BuildInfo), building or refreshing the database when needed."""
    from langchain_chroma import Chroma

    start = time.time()
    embeddings = embeddings or make_embeddings(settings)
    db_dir = Path(settings.vector_db_dir)
    manifest_path = db_dir / MANIFEST_NAME
    current = fingerprint(settings.knowledge_base_dir, settings)

    store = Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=str(db_dir),
        collection_metadata={"hnsw:space": "cosine"},
    )

    saved = {}
    if manifest_path.is_file():
        try:
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            saved = {}
    if not force_rebuild and saved.get("fingerprint") == current and store._collection.count() > 0:
        return store, BuildInfo(False, store._collection.count(), saved.get("files", 0), time.time() - start)

    log.info("Building the vector database from %s ...", settings.knowledge_base_dir)
    docs = load_documents(settings.knowledge_base_dir)
    chunks = split_documents(docs, settings.chunk_size, settings.chunk_overlap)

    # Same approach as the class notebook: drop the old collection, then add everything again
    store.delete_collection()
    store = Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=str(db_dir),
        collection_metadata={"hnsw:space": "cosine"},
    )
    ids = [f"{c.metadata['source']}#{c.metadata['chunk']}" for c in chunks]
    for i in range(0, len(chunks), 64):  # batches keep memory low on small servers
        store.add_documents(chunks[i : i + 64], ids=ids[i : i + 64])

    db_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "fingerprint": current,
                "files": len(docs),
                "chunks": len(chunks),
                "embedding_model": settings.embedding_model,
                "embedding_backend": EMBEDDING_BACKEND,
                "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    info = BuildInfo(True, len(chunks), len(docs), time.time() - start)
    log.info("Vector database ready: %d chunks from %d files in %.1fs", info.chunks, info.files, info.seconds)
    return store, info


@dataclass
class Hit:
    """One retrieved chunk, numbered for citations."""

    number: int
    text: str
    doc_type: str
    source: str
    title: str
    section: str
    score: float

    @property
    def label(self) -> str:
        return f"{self.source} › {self.section}"


def search(store, query: str, k: int) -> list[Hit]:
    results = store.similarity_search_with_relevance_scores(query, k=k)
    hits = []
    for n, (doc, score) in enumerate(results, start=1):
        meta = doc.metadata
        hits.append(
            Hit(
                number=n,
                text=strip_chunk_header(doc.page_content),
                doc_type=meta.get("doc_type", ""),
                source=meta.get("source", ""),
                title=meta.get("title", ""),
                section=meta.get("section", ""),
                score=max(0.0, min(1.0, float(score))),
            )
        )
    return hits
