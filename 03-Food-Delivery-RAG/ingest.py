"""Build the vector DB: turn knowledge-base/ into a Chroma vector database.

    python ingest.py                     # build, or reuse if nothing changed
    python ingest.py --force             # always rebuild
    python ingest.py --query "refund for a missing item"   # try a search

The app runs this automatically on start-up, so you only need it to inspect or force a rebuild.
The Render Docker image runs it at build time, so the live app starts with the DB ready.
"""

import argparse
import logging

from rag.config import Settings
from rag.knowledge_base import load_documents, open_vector_store, search, split_documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="rebuild even if the knowledge base is unchanged")
    parser.add_argument("--query", action="append", default=[], help="run a test search (can repeat)")
    parser.add_argument("--stats", action="store_true", help="print chunk counts per document")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    settings = Settings()
    if args.stats:
        chunks = split_documents(load_documents(settings.knowledge_base_dir), settings.chunk_size, settings.chunk_overlap)
        per_file: dict[str, int] = {}
        for c in chunks:
            per_file[c.metadata["source"]] = per_file.get(c.metadata["source"], 0) + 1
        for source, count in sorted(per_file.items()):
            print(f"{count:4d}  {source}")
        sizes = [len(c.page_content) for c in chunks]
        print(f"{len(chunks)} chunks · avg {sum(sizes) // len(sizes)} chars · max {max(sizes)} chars")

    store, info = open_vector_store(settings, force_rebuild=args.force)
    action = "Built" if info.rebuilt else "Loaded existing"
    print(f"{action} vector DB at {settings.vector_db_dir}: {info.chunks} chunks in {info.seconds:.1f}s")

    for query in args.query:
        print(f"\nQ: {query}")
        for hit in search(store, query, settings.top_k):
            print(f"  [{hit.number}] {hit.score:.2f}  {hit.label}")


if __name__ == "__main__":
    main()
