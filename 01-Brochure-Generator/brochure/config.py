"""Configuration: LLM provider settings and project paths."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Searches this folder and its parents for a .env file
load_dotenv(override=True)

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "outputs"


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str


def get_llm_config() -> LLMConfig | None:
    """Return Groq settings if a Groq key exists, else Gemini, else None."""
    if os.getenv("GROQ_API_KEY"):
        return LLMConfig(
            provider="Groq",
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=os.environ["GROQ_API_KEY"],
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        )
    if os.getenv("GOOGLE_API_KEY"):
        return LLMConfig(
            provider="Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.environ["GOOGLE_API_KEY"],
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        )
    return None
