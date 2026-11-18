"""Configuration: LLM provider settings and project paths."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "outputs"
# Hugging Face sets SPACE_ID when the app runs as a Space
ON_SPACES = bool(os.getenv("SPACE_ID"))


def _load_env() -> None:
    """Load the nearest .env (searching upward from this folder).

    Values in .env win over the shell, but blank lines such as `GOOGLE_API_KEY=`
    (copied straight from .env.example) are skipped, so they can't wipe out a
    key you already exported in your terminal.
    """
    path = find_dotenv()
    if not path:
        return
    for key, value in dotenv_values(path).items():
        if value and value.strip():
            os.environ[key] = value.strip()


_load_env()


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    key_env: str    # name of the env variable holding the key (for error messages)
    model_env: str  # name of the env variable that overrides the model


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def available_providers() -> dict[str, LLMConfig]:
    """Every provider that has an API key set, in order of preference."""
    providers: dict[str, LLMConfig] = {}
    if _env("GROQ_API_KEY"):
        providers["Groq"] = LLMConfig(
            provider="Groq",
            base_url=_env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=_env("GROQ_API_KEY"),
            model=_env("GROQ_MODEL", "openai/gpt-oss-120b"),
            key_env="GROQ_API_KEY",
            model_env="GROQ_MODEL",
        )
    if _env("GOOGLE_API_KEY"):
        providers["Gemini"] = LLMConfig(
            provider="Gemini",
            base_url=_env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            api_key=_env("GOOGLE_API_KEY"),
            model=_env("GEMINI_MODEL", "gemini-3.6-flash"),
            key_env="GOOGLE_API_KEY",
            model_env="GEMINI_MODEL",
        )
    return providers


def missing_key_message() -> str:
    if ON_SPACES:
        return ("This demo isn't set up yet: the Space owner needs to add GROQ_API_KEY "
                "under Settings → Variables and secrets.")
    return "No API key found. Add GROQ_API_KEY (or GOOGLE_API_KEY) to your .env file and restart the app."


def get_llm_config(provider: str | None = None) -> LLMConfig | None:
    """Settings for `provider`, or for the first available one (Groq, then Gemini)."""
    providers = available_providers()
    if provider:
        return providers.get(provider)
    return next(iter(providers.values()), None)
