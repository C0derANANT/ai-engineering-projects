"""Settings: API keys, model names and limits.

Everything can be overridden with environment variables (or a .env file next to app.py),
so the same code runs on a laptop and on Render.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"

# Real environment variables (for example Render's) win over .env
load_dotenv(ENV_FILE, override=False)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def get_secret(name: str) -> str | None:
    """Return an API key, or None if it isn't set.

    The .env file is read again on every call, so a key pasted into .env while the app
    is running is picked up without a restart.
    """
    value = os.environ.get(name, "").strip()
    if not value and ENV_FILE.is_file():
        value = (dotenv_values(ENV_FILE).get(name) or "").strip()
    return value or None


def server_options(environ=None) -> dict:
    """Where Gradio should listen: 0.0.0.0:$PORT on hosts like Render, Gradio's defaults locally."""
    environ = os.environ if environ is None else environ
    port = str(environ.get("PORT", "")).strip()
    if not port.isdigit() or not 0 < int(port) < 65536:
        return {}
    return {"server_name": "0.0.0.0", "server_port": int(port)}


@dataclass(frozen=True)
class Settings:
    groq_model: str = field(default_factory=lambda: os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))
    # Other Groq models tried, in order, when the main one hits its per-minute token limit
    # (each model has its own limit). Comma-separated; "" turns them off.
    groq_backup_models: tuple[str, ...] = field(default_factory=lambda: tuple(
        m.strip() for m in os.environ.get("GROQ_BACKUP_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",")
        if m.strip()
    ))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
    whisper_model: str = field(default_factory=lambda: os.environ.get("WHISPER_MODEL", "whisper-large-v3-turbo"))
    llm_timeout_seconds: int = 60

    # Guard rails
    max_question_chars: int = 1000
    max_history_messages: int = 6  # the last 3 exchanges
    max_history_chars_per_message: int = 900  # Groq's free tier allows 8,000 tokens a minute per model
    max_tool_rounds: int = 5
    max_tool_result_chars: int = 6000
