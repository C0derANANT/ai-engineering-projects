"""
AI Movie: a chatbot that answers any question about any movie, with facts from Wikipedia.

Ask about a film's director, cast and characters, production house, budget, box office,
release date, plot or verdict (flop / hit / blockbuster), in English, Hindi or Hinglish,
by typing or with the mic.

Stack (as in the Incapp AI Engineer class, plus upgrades):
    - openai SDK -> Groq gpt-oss-120b (Gemini as automatic backup)   -> answers + tool calls
    - Wikipedia API (no key needed)                                  -> the facts
    - Groq Whisper                                                   -> voice questions
    - Gradio ChatInterface                                           -> the chat UI

Run:
    pip install -r requirements.txt
    cp .env.example .env        # add your GROQ_API_KEY
    python app.py
"""

import logging

import gradio as gr

from movie.assistant import HEARD_PREFIX, Assistant
from movie.config import Settings, get_secret, server_options
from movie.voice import VoiceError, is_audio, transcribe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpcore", "urllib3", "openai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

settings = Settings()
assistant = Assistant(settings)

EXAMPLES = [
    "Tell me everything about the movie Inception",
    "Who directed 3 Idiots and was it a hit?",
    "Pathaan ka budget aur box office collection kitna tha?",
    "बाहुबली 2 में मुख्य किरदार किसने निभाए?",
    "Compare Jawan and Pathaan: budget, box office and verdict",
    "What is the plot of Sholay, without spoilers?",
]

HEADER = """# 🎬 AI Movie
Ask anything about any movie (director, cast and characters, budget, box office, release date, plot, hit or flop) in **English, हिंदी or Hinglish**, typed or 🎙️ spoken. Facts come live from **Wikipedia**, with links under every answer."""

ABOUT = """### How it works
1. Your question (typed, or 🎙️ transcribed by Groq Whisper) goes to **gpt-oss-120b on Groq**.
2. The model calls tools that read **Wikipedia**: `get_movie` (infobox facts and summary), `get_movie_section` (plot, cast, box office, reviews, awards) and `search_movies` (when the title is unclear).
3. It answers from those facts in your language, and the app adds links to the pages it used.
4. If Groq is busy, **Gemini** answers instead.

Numbers come from Wikipedia, so they're only as current as the article. Built for the Incapp AI Engineer course."""


def split_message(message) -> tuple[str, list[str]]:
    """A multimodal textbox gives {"text": ..., "files": [...]}; a plain one gives a string."""
    if isinstance(message, dict):
        files = []
        for f in message.get("files") or []:
            path = f.get("path") if isinstance(f, dict) else f
            if path:
                files.append(str(path))
        return (message.get("text") or "").strip(), files
    return (message or "").strip() if isinstance(message, str) else "", []


def respond(message, history):
    text, files = split_message(message)
    prefix = ""
    audio = next((f for f in files if is_audio(f)), None)
    if audio:
        try:
            spoken = transcribe(audio, settings)
        except VoiceError as exc:
            yield f"🎙️ {exc}"
            return
        prefix = f"{HEARD_PREFIX}{spoken}”\n\n"
        text = f"{text} {spoken}".strip() if text else spoken
    elif files and not text:
        yield "I can only read text and voice recordings. Please type your question or use the mic."
        return

    for reply in assistant.respond(text, history):
        yield prefix + reply.text


with gr.Blocks(title="AI Movie · movie facts from Wikipedia", fill_height=True) as demo:
    gr.Markdown(HEADER)
    if not (get_secret("GROQ_API_KEY") or get_secret("GOOGLE_API_KEY")):
        gr.Markdown("⚠️ No API key found: add `GROQ_API_KEY` to `.env` (or the server's environment) to turn on answers.")
    gr.ChatInterface(
        fn=respond,
        multimodal=True,
        textbox=gr.MultimodalTextbox(
            placeholder="Ask about any movie, or press 🎙️ and speak…",
            sources=["microphone"],
            file_types=["audio"],
            autofocus=True,
        ),
        chatbot=gr.Chatbot(layout="bubble", height=560, buttons=["copy"]),
        examples=EXAMPLES,
        cache_examples=False,
        fill_height=True,
    )
    with gr.Accordion("How it works", open=False):
        gr.Markdown(ABOUT)


def launch(**kwargs):
    """Start the app. On Render, $PORT is set, so it listens on 0.0.0.0:$PORT."""
    return demo.queue(default_concurrency_limit=8).launch(
        theme=gr.themes.Soft(primary_hue="red", secondary_hue="amber"),
        **{**server_options(), **kwargs},
    )


if __name__ == "__main__":
    launch()
