"""
AI Movie - a generative AI chat app that answers any question about movies.

Ask about a movie's director, hero/cast, characters, production house,
budget, release date, box office verdict (flop / hit / super hit), and more.

Stack (same as the Incapp AI Engineer class):
    - openai      : OpenAI-compatible client, pointed at Groq (or Gemini)
    - gradio      : ChatInterface for the chat UI
    - python-dotenv: loads API keys from .env

Run:
    pip install -r requirements.txt
    python app.py
"""

import os  # Read API keys from environment variables
from dotenv import load_dotenv  # Load keys from the .env file
from openai import OpenAI  # OpenAI-compatible client (works with Groq and Gemini)
import gradio as gr  # Chat UI

load_dotenv(override=True)  # Load .env from this folder

# ---------------------------------------------------------------------------
# LLM setup: use Groq if GROQ_API_KEY is set, otherwise fall back to Gemini
# ---------------------------------------------------------------------------
if os.getenv("GROQ_API_KEY"):
    BASE_URL = "https://api.groq.com/openai/v1"  # Groq API
    api_key = os.getenv("GROQ_API_KEY")
    MODEL = "openai/gpt-oss-120b"
    PROVIDER = "Groq"
elif os.getenv("GOOGLE_API_KEY"):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"  # Gemini API
    api_key = os.getenv("GOOGLE_API_KEY")
    MODEL = "gemini-3.6-flash"
    PROVIDER = "Gemini"
else:
    raise SystemExit(
        "No API key found. Copy .env.example to .env and add your GROQ_API_KEY "
        "(or GOOGLE_API_KEY)."
    )

myAI = OpenAI(base_url=BASE_URL, api_key=api_key)  # Create the client

# ---------------------------------------------------------------------------
# System prompt: keeps the bot focused on movies only
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are "AI Movie", an expert movie encyclopedia assistant.

You answer ANY question about movies from any industry
(Bollywood, Hollywood, Tollywood, Kollywood, and world cinema), for example:
- Director, producer, writer and music director
- Hero / heroine / lead cast and the characters they played
- Production house and distributor
- Budget and box office collection
- Release date and runtime
- Verdict: Flop, Average, Hit, Super Hit, Blockbuster
- Plot summary (no major spoilers unless the user asks), genre, awards, trivia

Rules:
1. Only answer questions related to movies, actors, and the film industry.
   If the user asks about something else, politely say you only answer movie questions.
2. Use clear headings and bullet points. For a general question about a movie,
   give a short "Movie Card" with: Director, Lead Cast, Production House,
   Release Date, Budget, Box Office, Verdict.
3. Budget and box office figures are approximate; mention the currency
   (e.g. ₹ crore or $ million) and say "approx." when unsure.
4. If you don't know or the movie may not exist, say so honestly. Never invent facts.
5. If the user writes in Hinglish or Hindi, reply in the same style.
"""


def to_text(content):
    """Gradio can send message content as a string or a list of parts; return plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content or "")


def ask_movie_ai(prompt, history):
    """Called by Gradio for every message; streams the answer back."""
    # Keep only role + text from the chat history (drop Gradio-specific fields)
    past = [
        {"role": m["role"], "content": to_text(m["content"])}
        for m in history
        if m.get("role") in ("user", "assistant")
    ]

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + past
        + [{"role": "user", "content": prompt}]
    )

    try:
        response = myAI.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=True,  # Stream the answer word by word
        )
        res = ""
        for chunk in response:
            if chunk.choices:
                res += chunk.choices[0].delta.content or ""
                yield res
    except Exception as e:  # Show API errors in the chat instead of crashing
        yield f"⚠️ Error from {PROVIDER}: {e}"


demo = gr.ChatInterface(
    fn=ask_movie_ai,
    title="🎬 AI Movie",
    description=(
        "Ask anything about any movie: director, hero, characters, budget, "
        f"release date, hit or flop. Powered by {PROVIDER} + Gradio."
    ),
    examples=[
        "Who directed 3 Idiots and was it a hit?",
        "Tell me everything about the movie Inception",
        "Pathaan ka budget aur box office collection kitna tha?",
        "Which production house made Baahubali and who played the main characters?",
    ],
)

if __name__ == "__main__":
    demo.launch(inbrowser=True, share=True)
