"""Settings for the assistant: paths, model names and limits.

Everything can be overridden with environment variables (or a .env file next to app.py),
so the same code runs on a laptop, in Colab and on Hugging Face Spaces.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"

# Real environment variables (for example Hugging Face Space secrets) win over .env
load_dotenv(ENV_FILE, override=False)


def get_secret(name: str) -> str | None:
    """Return an API key, or None if it isn't set.

    The .env file is read again on every call, so a key pasted into .env while the
    app is running is picked up without a restart.
    """
    value = os.environ.get(name, "").strip()
    if not value and ENV_FILE.is_file():
        value = (dotenv_values(ENV_FILE).get(name) or "").strip()
    return value or None


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    knowledge_base_dir: Path = field(
        default_factory=lambda: _env_path("KNOWLEDGE_BASE_DIR", PROJECT_DIR / "knowledge-base")
    )
    vector_db_dir: Path = field(
        default_factory=lambda: _env_path("VECTOR_DB_DIR", PROJECT_DIR / "vector_db")
    )
    orders_file: Path = field(
        default_factory=lambda: _env_path("ORDERS_FILE", PROJECT_DIR / "data" / "sample_orders.json")
    )
    collection_name: str = "cravecart_kb"

    # Retrieval
    embedding_model: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    )
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = field(default_factory=lambda: _env_int("TOP_K", 5))

    # LLMs (same Groq model as the class notebooks; Gemini is an optional backup)
    groq_model: str = field(default_factory=lambda: os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))
    # Small, fast model for rewriting questions; it has its own Groq rate limit
    rewrite_model: str = field(default_factory=lambda: os.environ.get("REWRITE_MODEL", "openai/gpt-oss-20b"))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
    whisper_model: str = field(
        default_factory=lambda: os.environ.get("WHISPER_MODEL", "whisper-large-v3-turbo")
    )
    llm_timeout_seconds: int = 60

    # Guard rails for odd input
    max_question_chars: int = 2000
    max_history_messages: int = 8  # last 4 exchanges
    max_history_chars_per_message: int = 1500
    max_tool_rounds: int = 4
