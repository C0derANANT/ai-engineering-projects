"""Builds the prompt and streams the brochure from the LLM."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

from .config import get_llm_config
from .scraper import WebsiteContext

logger = logging.getLogger(__name__)

TONES = {
    "Professional": "a formal, confident corporate tone",
    "Friendly": "a warm, approachable and conversational tone",
    "Witty / Creative": "a witty, modern and creative tone (clever, never cringe)",
    "Premium / Luxury": "an elegant, premium tone with refined language",
}
FORMATS = {
    "Bullet points": "Use concise bullet points for services, features and benefits.",
    "Paragraphs": "Use short descriptive paragraphs throughout.",
    "Mixed": "Use paragraphs for the overview and vision, bullet points for services and benefits.",
}
LENGTHS = {
    "Short": "Keep it to roughly 200-300 words.",
    "Standard": "Aim for roughly 400-600 words.",
    "Detailed": "Aim for roughly 700-1000 words.",
}


class BrochureError(Exception):
    """A user-facing error (missing key, bad input, API failure)."""


@dataclass
class BrochureRequest:
    company_name: str
    tone: str = "Professional"
    format: str = "Mixed"
    length: str = "Standard"
    audience: str = ""
    website: WebsiteContext | None = None


SYSTEM_PROMPT = """You are a world-class corporate copywriter who writes company brochures.

Write the brochure in clean Markdown with exactly this structure:
# <Catchy headline that includes the company name>
A one-line tagline in *italics*.
## About Us
## Our Services & Products
## Technologies & Expertise
## Why Choose Us
## Our Culture   (only if the source material says something about culture or careers)
## Get in Touch

Style:
- Write in {tone}.
- {format}
- {length}
{audience}
Accuracy rules (very important):
- Use only facts found in the website content. If there is no website content,
  write general but plausible copy based on the company name and never state
  specific numbers, clients, awards or dates.
- Never invent phone numbers, emails or addresses. In "Get in Touch" use
  placeholders like [Phone], [Email], [Address] unless they appear in the source.
- Do not use emojis, tables, HTML or code blocks. Use **bold** sparingly.
"""


def _build_messages(req: BrochureRequest) -> list[dict]:
    audience = f"- The target audience is: {req.audience.strip()}.\n" if req.audience.strip() else ""
    system = SYSTEM_PROMPT.format(
        tone=TONES.get(req.tone, TONES["Professional"]),
        format=FORMATS.get(req.format, FORMATS["Mixed"]),
        length=LENGTHS.get(req.length, LENGTHS["Standard"]),
        audience=audience,
    )
    source = req.website.as_prompt() if req.website else "No website was provided."
    user = (
        f"Company name: {req.company_name.strip()}\n\n"
        f"Website content:\n{source}\n\n"
        "Write the brochure now."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def stream_brochure(req: BrochureRequest) -> Iterator[str]:
    """Yield the brochure Markdown as it grows. Raises BrochureError on failure."""
    if not req.company_name.strip():
        raise BrochureError("Please enter a company name.")

    config = get_llm_config()
    if config is None:
        raise BrochureError(
            "No API key found. Add GROQ_API_KEY (or GOOGLE_API_KEY) to your .env file."
        )

    client = OpenAI(base_url=config.base_url, api_key=config.api_key, timeout=60)
    try:
        stream = client.chat.completions.create(
            model=config.model,
            messages=_build_messages(req),
            temperature=0.7,
            stream=True,
        )
        text = ""
        for chunk in stream:
            if chunk.choices:
                text += chunk.choices[0].delta.content or ""
                yield text
    except OpenAIError as e:
        logger.exception("LLM request failed")
        raise BrochureError(f"{config.provider} API error: {e}") from e

    if not text.strip():
        raise BrochureError("The model returned an empty response. Please try again.")
