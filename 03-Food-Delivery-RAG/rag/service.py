"""Wires the pieces together once: vector DB + demo orders + tools + models -> Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .assistant import Assistant
from .config import Settings
from .knowledge_base import BuildInfo, open_vector_store, search
from .llm import get_models
from .orders import OrderStore
from .tools import build_tools

log = logging.getLogger(__name__)

# Keep the console readable: these libraries log every HTTP request at INFO level
for noisy in ("httpx", "httpcore", "urllib3", "huggingface_hub", "sentence_transformers", "chromadb"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


@dataclass
class Service:
    settings: Settings
    assistant: Assistant
    orders: OrderStore
    db_info: BuildInfo
    store: object


def build_service(settings: Settings | None = None, embeddings=None) -> Service:
    settings = settings or Settings()
    store, info = open_vector_store(settings, embeddings=embeddings)
    orders = OrderStore.from_file(settings.orders_file)
    assistant = Assistant(
        settings=settings,
        search_fn=lambda query, k: search(store, query, k),
        tools=build_tools(orders),
        models_fn=lambda: get_models(settings),
        order_ids=orders.ids(),
    )
    return Service(settings, assistant, orders, info, store)
