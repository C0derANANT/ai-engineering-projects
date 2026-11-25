"""
Crave Assist: a RAG help assistant for CraveCart, a fictional Zomato-style food delivery company.

Stack (as in the Incapp AI Engineer class, plus upgrades):
    - LangChain + Chroma + Hugging Face embeddings (BAAI/bge-small-en-v1.5)  -> the RAG_DB
    - Groq gpt-oss-120b (Gemini as automatic backup)                        -> answers + tool calls
    - Groq Whisper                                                           -> voice questions
    - Gradio ChatInterface                                                   -> the chat UI

Run:
    pip install -r requirements.txt
    cp .env.example .env        # add your GROQ_API_KEY
    python app.py               # builds the vector DB on first run, then opens the app
"""

import logging

import gradio as gr

from rag.assistant import HEARD_PREFIX
from rag.config import get_secret
from rag.service import build_service
from rag.ui import ABOUT, CSS, EMPTY_SOURCES, EXAMPLES, HEADER, sources_markdown, split_message
from rag.voice import VoiceError, is_audio, transcribe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

service = build_service()  # builds or loads the vector DB (first run: about a minute)
log.info("Ready: %d chunks in the vector DB, %d demo orders", service.db_info.chunks, len(service.orders.ids()))


def respond(message, history):
    text, files = split_message(message)
    notes, heard = [], ""

    audio = [f for f in files if is_audio(f)]
    if len(audio) < len(files):
        notes.append("_I can only listen to voice recordings, so other attached files were ignored._")
    if audio:
        try:
            spoken = transcribe(audio[-1], service.settings)
        except VoiceError as exc:
            if not text:
                yield f"🎙️ {exc}", EMPTY_SOURCES
                return
            notes.append(f"_🎙️ {exc} Answering your typed question instead._")
        else:
            heard = f"{HEARD_PREFIX}{spoken}”\n\n"
            text = f"{text}\n{spoken}" if text else spoken

    head = heard + ("\n\n".join(notes) + "\n\n" if notes else "")
    if not text:
        yield head + "Please type a question, or tap the 🎙️ microphone and ask out loud.", EMPTY_SOURCES
        return

    try:
        for reply in service.assistant.respond(text, history):
            yield head + reply.text, sources_markdown(reply)
    except Exception:  # never show users a stack trace
        log.exception("Unexpected error while answering")
        yield head + "⚠️ Sorry, something went wrong on our side. Please try again.", EMPTY_SOURCES


with gr.Blocks(title="Crave Assist · CraveCart RAG demo", fill_height=True) as demo:
    gr.HTML(HEADER)
    if not get_secret("GROQ_API_KEY") and not get_secret("GOOGLE_API_KEY"):
        gr.Markdown(
            "> ⚠️ **No API key configured.** The app will show matching help passages but can't write "
            "answers. Add `GROQ_API_KEY` to `.env` (or as a Space secret) to turn on AI answers."
        )

    sources = gr.Markdown(EMPTY_SOURCES, elem_id="sources-panel", render=False)

    with gr.Row(equal_height=False):
        with gr.Column(scale=7, min_width=340):
            gr.ChatInterface(
                fn=respond,
                multimodal=True,
                textbox=gr.MultimodalTextbox(
                    placeholder="Ask about orders, refunds, fees, the app or HR policies… or tap 🎙️ to speak",
                    sources=["microphone"],
                    file_types=["audio"],
                    max_lines=6,
                ),
                chatbot=gr.Chatbot(height=560, show_label=False, layout="bubble", buttons=["copy"]),
                additional_outputs=[sources],
                examples=[{"text": e} for e in EXAMPLES],
                save_history=True,
                autofocus=True,
                fill_height=True,
                concurrency_limit=8,
            )
        with gr.Column(scale=5, min_width=300):
            with gr.Tab("📚 Sources"):
                sources.render()
            with gr.Tab("📦 Demo orders"):
                gr.Markdown("Ask about any of these, for example *“Cancel #1043, what do I get back?”*")
                gr.Dataframe(
                    value=service.orders.table(),
                    headers=["Order", "Restaurant", "Status", "What it shows"],
                    interactive=False,
                    wrap=True,
                )
            with gr.Tab("ℹ️ How it works"):
                gr.Markdown(ABOUT)


def launch(**kwargs):
    """Start the app (also used by notebooks/RAG_APP.ipynb, e.g. launch(share=True) in Colab)."""
    return demo.queue(default_concurrency_limit=8).launch(
        theme=gr.themes.Soft(primary_hue="orange", secondary_hue="amber"),
        css=CSS,
        **kwargs,
    )


if __name__ == "__main__":
    launch()
