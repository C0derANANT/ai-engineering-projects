"""
Crave Assist: a RAG demo that answers questions about CraveCart, a fictional food delivery company.

Stack (as in the Incapp AI Engineer class, plus upgrades):
    - LangChain + Chroma + BGE embeddings (BAAI/bge-small-en-v1.5, ONNX)    -> the vector DB
    - Groq gpt-oss-20b (rewrites the question) + gpt-oss-120b (answers)     -> the LLMs
    - Gradio ChatInterface + a Sources panel                                 -> the UI

Run:
    pip install -r requirements.txt
    cp .env.example .env        # add your GROQ_API_KEY
    python app.py               # builds the vector DB on first run, then opens the app
"""

import logging

import gradio as gr

from rag.assistant import Assistant
from rag.config import Settings, get_secret, server_options
from rag.knowledge_base import open_vector_store, search
from rag.ui import ABOUT, CSS, EMPTY_SOURCES, EXAMPLES, HEADER, sources_markdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Keep the console readable: these libraries log every HTTP request at INFO level
for noisy in ("httpx", "httpcore", "urllib3", "huggingface_hub", "fastembed", "chromadb"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("app")

settings = Settings()
store, db_info = open_vector_store(settings)  # builds or loads the vector DB (first run: about a minute)
assistant = Assistant(settings, search_fn=lambda query, k: search(store, query, k))
log.info("Ready: %d chunks in the vector DB", db_info.chunks)


def respond(message, history):
    """Called by Gradio for every message: streams (answer so far, Sources panel)."""
    try:
        for reply in assistant.respond(message, history):
            yield reply.text, sources_markdown(reply)
    except Exception:  # never show users a stack trace
        log.exception("Unexpected error while answering")
        yield "⚠️ Sorry, something went wrong on our side. Please try again.", EMPTY_SOURCES


with gr.Blocks(title="Crave Assist · CraveCart RAG demo", fill_height=True) as demo:
    gr.HTML(HEADER)
    if not get_secret("GROQ_API_KEY"):
        gr.Markdown(
            "> ⚠️ **No API key configured.** The app will show matching help passages but can't write "
            "answers. Add `GROQ_API_KEY` to `.env` to turn on AI answers."
        )

    sources = gr.Markdown(EMPTY_SOURCES, elem_id="sources-panel", render=False)

    with gr.Row(equal_height=False):
        with gr.Column(scale=7, min_width=340):
            gr.ChatInterface(
                fn=respond,
                textbox=gr.Textbox(
                    placeholder="Ask about ordering, fees, cancellations, refunds, the app or HR policies…",
                    max_lines=6,
                    show_label=False,
                ),
                chatbot=gr.Chatbot(height=560, show_label=False, layout="bubble", buttons=["copy"]),
                additional_outputs=[sources],
                examples=EXAMPLES,
                save_history=True,
                autofocus=True,
                fill_height=True,
                concurrency_limit=8,
            )
        with gr.Column(scale=5, min_width=300):
            with gr.Tab("📚 Sources"):
                sources.render()
            with gr.Tab("ℹ️ How it works"):
                gr.Markdown(ABOUT)


def launch(**kwargs):
    """Start the app (also used by notebooks/02_chat_app.ipynb, e.g. launch(share=True) in Colab).

    On Render, $PORT is set, so the app listens on 0.0.0.0:$PORT.
    """
    return demo.queue(default_concurrency_limit=8).launch(
        theme=gr.themes.Soft(primary_hue="orange", secondary_hue="amber"),
        css=CSS,
        **{**server_options(), **kwargs},
    )


if __name__ == "__main__":
    launch()
