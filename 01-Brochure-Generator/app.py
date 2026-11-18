"""
AI Company Brochure Generator - Gradio web app.

Enter a company name (and optionally its website). The app scrapes the
website, asks an LLM (Groq or Gemini) to write a brochure, streams the preview,
and exports it as a styled PDF and DOCX.

Run:
    pip install -r requirements.txt
    python app.py            # opens locally + creates a public share link
"""

import argparse
import logging

import gradio as gr

from brochure import (
    BrochureError,
    BrochureRequest,
    ScrapeError,
    export_docx,
    export_pdf,
    fetch_website_context,
    make_basename,
    normalize_url,
    stream_brochure,
)
from brochure.config import OUTPUT_DIR, get_llm_config
from brochure.generator import FORMATS, LENGTHS, TONES

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# Keep logs readable: hide per-request HTTP noise from libraries
for noisy in ("httpx", "urllib3", "openai", "fontTools"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger("brochure_app")


def generate(company_name, website, audience, tone, fmt, length, progress=gr.Progress()):
    """Gradio handler: yields (preview_markdown, pdf_file, docx_file)."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise gr.Error("Please enter a company name.")
    if get_llm_config() is None:  # Fail fast instead of scraping first
        raise gr.Error("No API key found. Add GROQ_API_KEY (or GOOGLE_API_KEY) to your .env file and restart the app.")

    website_ctx = None
    if (website or "").strip():
        url = normalize_url(website)
        if url is None:
            raise gr.Error("That website doesn't look valid. Try something like https://example.com")
        progress(0.1, desc="Reading website...")
        try:
            website_ctx = fetch_website_context(url)
        except ScrapeError as e:
            gr.Warning(f"Couldn't read {url}: {e}. The brochure will be based on the company name only.")
        else:
            if website_ctx.is_thin:
                gr.Warning(
                    f"{url} returned almost no readable text (it probably loads its content with "
                    "JavaScript), so the brochure will be mostly generic."
                )

    request = BrochureRequest(
        company_name=company_name,
        tone=tone,
        format=fmt,
        length=length,
        audience=audience or "",
        website=website_ctx,
    )

    progress(0.3, desc="Writing brochure...")
    markdown = ""
    try:
        for markdown in stream_brochure(request, on_warning=gr.Warning):
            yield markdown, None, None
    except BrochureError as e:
        raise gr.Error(str(e))

    progress(0.9, desc="Creating PDF and DOCX...")
    try:
        basename = make_basename(company_name)
        pdf_path = export_pdf(markdown, company_name, basename)
        docx_path = export_docx(markdown, company_name, basename)
    except Exception as e:  # Show the preview even if exporting fails
        logger.exception("Export failed")
        gr.Warning(f"Brochure created, but exporting failed: {e}")
        yield markdown, None, None
        return

    logger.info("Saved %s and %s", pdf_path.name, docx_path.name)
    yield markdown, str(pdf_path), str(docx_path)


def build_ui() -> gr.Blocks:
    config = get_llm_config()
    provider_note = (
        f"Powered by **{config.provider}** (`{config.model}`)."
        if config
        else "⚠️ **No API key found.** Add `GROQ_API_KEY` to your `.env` file."
    )

    with gr.Blocks(title="AI Brochure Generator") as demo:
        gr.Markdown(
            "# 🏢 AI Company Brochure Generator\n"
            "Turn any company's website into a polished brochure, ready to download "
            f"as PDF or Word. {provider_note}"
        )

        with gr.Row():
            with gr.Column(scale=2):
                company_name = gr.Textbox(label="Company name", placeholder="e.g. Hugging Face")
                website = gr.Textbox(
                    label="Website (optional, but gives much better results)",
                    placeholder="e.g. huggingface.co",
                )
                audience = gr.Textbox(
                    label="Target audience (optional)",
                    placeholder="e.g. investors, job seekers, enterprise clients",
                )
                tone = gr.Radio(list(TONES), value="Professional", label="Tone")
                fmt = gr.Radio(list(FORMATS), value="Mixed", label="Format")
                length = gr.Radio(list(LENGTHS), value="Standard", label="Length")
                generate_btn = gr.Button("Generate Brochure ✨", variant="primary")

                gr.Examples(
                    examples=[
                        ["Hugging Face", "https://huggingface.co", "developers and AI teams"],
                        ["Groq", "https://groq.com", "enterprise clients"],
                        ["Chai Point", "", "young professionals"],
                    ],
                    inputs=[company_name, website, audience],
                )

            with gr.Column(scale=3):
                preview = gr.Markdown(
                    "*Your brochure preview will appear here.*",
                    container=True,
                    min_height=420,
                )
                with gr.Row():
                    pdf_file = gr.File(label="Download PDF")
                    docx_file = gr.File(label="Download DOCX")

        inputs = [company_name, website, audience, tone, fmt, length]
        outputs = [preview, pdf_file, docx_file]
        generate_btn.click(generate, inputs=inputs, outputs=outputs)
        company_name.submit(generate, inputs=inputs, outputs=outputs)

    return demo


def main():
    parser = argparse.ArgumentParser(description="AI Company Brochure Generator")
    parser.add_argument("--port", type=int, default=None, help="Port to run on (default: auto)")
    parser.add_argument("--no-share", action="store_true", help="Don't create a public share link")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_ui().launch(
        share=not args.no_share,
        server_port=args.port,
        inbrowser=not args.no_browser,
        theme=gr.themes.Soft(),
        allowed_paths=[str(OUTPUT_DIR)],
    )


if __name__ == "__main__":
    main()
