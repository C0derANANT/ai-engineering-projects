"""
AI Company Brochure Generator - Gradio web app.

Enter a company name (and optionally its website). The app scrapes the
website, asks an LLM (Groq or Gemini) to write a brochure in the chosen
language, tone and sections, streams the preview, and exports it as a PDF and
DOCX in your brand colour.

Run:
    pip install -r requirements.txt
    python app.py            # opens in your browser (local only)
    python app.py --share    # also creates a temporary public link
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
from brochure.config import HOSTED, OUTPUT_DIR, get_llm_config, missing_key_message
from brochure.exporters import DEFAULT_COLOR, find_placeholders
from brochure.generator import DEFAULT_SECTIONS, FORMATS, LANGUAGES, LENGTHS, SECTIONS, TONES

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# Keep logs readable: hide per-request HTTP noise from libraries
for noisy in ("httpx", "urllib3", "openai", "fontTools", "fpdf"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger("brochure_app")

# company, website, audience, tone, format, length, language, sections, brand colour
EXAMPLES = [
    ["Hugging Face", "huggingface.co", "developers and AI teams", "Friendly", "Mixed", "Standard",
     "English", ["About Us", "Mission & Vision", "Our Services & Products", "Why Choose Us", "Get in Touch"],
     "#ffd21e"],
    ["Groq", "groq.com", "enterprise CTOs", "Professional", "Bullet points", "Short",
     "English", ["About Us", "Our Services & Products", "Technologies & Expertise", "Get in Touch"],
     "#f55036"],
    ["Chai Point", "chaipoint.com", "young professionals in India", "Witty / Creative", "Mixed", "Standard",
     "Hindi", ["About Us", "Our Services & Products", "Our Culture", "Get in Touch"],
     "#2e7d32"],
    ["Stripe", "stripe.com", "startup founders", "Premium / Luxury", "Paragraphs", "Detailed",
     "Spanish", ["About Us", "Mission & Vision", "Our Services & Products", "Why Choose Us", "FAQ", "Get in Touch"],
     "#635bff"],
    ["Blue Tokai Coffee", "", "cafe owners", "Friendly", "Bullet points", "Short",
     "English", DEFAULT_SECTIONS, "#6f4e37"],
]
EXAMPLE_LABELS = [
    "Hugging Face · friendly · yellow",
    "Groq · short bullet points",
    "Chai Point · in Hindi",
    "Stripe · detailed, in Spanish + FAQ",
    "Blue Tokai · no website",
]


def _export(markdown: str, company_name: str, color: str, logo: bytes | None = None) -> tuple[str, str]:
    basename = make_basename(company_name)
    pdf_path = export_pdf(markdown, company_name, basename, color=color, logo=logo)
    docx_path = export_docx(markdown, company_name, basename, color=color, logo=logo)
    logger.info("Saved %s and %s", pdf_path.name, docx_path.name)
    return str(pdf_path), str(docx_path)


def _status(markdown: str, edited: bool = False):
    """The note under the preview: unsaved edits and placeholders still to fill in."""
    notes = []
    if edited:
        notes.append("✏️ You've edited the text. Press **Update PDF & DOCX** to put your changes in the downloads.")
    if placeholders := find_placeholders(markdown):
        listed = ", ".join(f"`{p}`" for p in placeholders)
        notes.append(
            f"**Fill in the blanks:** the website didn't give {listed}, so the AI left a placeholder "
            "instead of making something up. Replace them in the **Edit** tab, or leave them: "
            "lines that still have a placeholder are left out of the PDF and DOCX."
        )
    return gr.Markdown("\n\n".join(notes), visible=bool(notes))


def on_edit(markdown):
    """Live preview while the user types in the Edit tab."""
    return markdown, _status(markdown, edited=True)


def reexport(brochure, markdown, color):
    """Export the brochure again, with the user's edits and the current brand colour
    (no new AI call)."""
    if not brochure or not (markdown or "").strip():
        return gr.skip(), gr.skip(), gr.skip()
    try:
        pdf_path, docx_path = _export(markdown, brochure["company"], color, brochure.get("logo"))
    except Exception as e:
        logger.exception("Re-export failed")
        raise gr.Error(f"Couldn't update the files: {e}")
    return pdf_path, docx_path, _status(markdown)


def generate(company_name, website, audience, tone, fmt, length, language, sections, color,
             progress=gr.Progress()):
    """Gradio handler: yields (preview, pdf_file, docx_file, last_brochure, editor, note)."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise gr.Error("Please enter a company name.")
    if not sections:
        raise gr.Error("Pick at least one section to include.")
    if get_llm_config() is None:  # Fail fast instead of scraping first
        raise gr.Error(missing_key_message())

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
        language=language or "English",
        sections=list(sections),
    )

    progress(0.3, desc="Writing brochure...")
    markdown = ""
    hidden_note = gr.Markdown(visible=False)
    try:
        for markdown in stream_brochure(request, on_warning=gr.Warning):
            # The editor fills in once the brochure is finished
            yield markdown, None, None, None, "", hidden_note
    except BrochureError as e:
        raise gr.Error(str(e))

    # Kept for re-exports after an edit or colour change (no new scrape or AI call)
    brochure = {"company": company_name, "logo": website_ctx.logo if website_ctx else None}
    progress(0.9, desc="Creating PDF and DOCX...")
    try:
        pdf_path, docx_path = _export(markdown, company_name, color, brochure["logo"])
    except Exception as e:  # Show the preview even if exporting fails
        logger.exception("Export failed")
        gr.Warning(f"Brochure created, but exporting failed: {e}")
        yield markdown, None, None, brochure, markdown, _status(markdown)
        return

    yield markdown, pdf_path, docx_path, brochure, markdown, _status(markdown)


def build_ui() -> gr.Blocks:
    config = get_llm_config()
    provider_note = (
        f"Powered by **{config.provider}** (`{config.model}`)."
        if config
        else f"⚠️ {missing_key_message()}"
    )
    demo_note = (
        "\n\n*Free public demo: the AI has a per-minute limit, so if it's busy, wait a minute "
        "and try again. After a quiet spell the site needs about a minute to wake up.*" if HOSTED else ""
    )

    with gr.Blocks(title="AI Brochure Generator") as demo:
        gr.Markdown(
            "# 🏢 AI Company Brochure Generator\n"
            "Turn any company's website into a polished brochure, ready to download "
            f"as PDF or Word. {provider_note}{demo_note}"
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
                with gr.Row():
                    language = gr.Dropdown(LANGUAGES, value="English", label="Language", scale=2)
                    color = gr.ColorPicker(
                        value=DEFAULT_COLOR, label="Brand colour", scale=1,
                        info="Title banner and headings",
                    )
                tone = gr.Radio(list(TONES), value="Professional", label="Tone")
                fmt = gr.Radio(list(FORMATS), value="Mixed", label="Format")
                length = gr.Radio(list(LENGTHS), value="Standard", label="Length")
                sections = gr.CheckboxGroup(
                    list(SECTIONS), value=DEFAULT_SECTIONS, label="Sections to include",
                )
                generate_btn = gr.Button("Generate Brochure ✨", variant="primary")

            with gr.Column(scale=3):
                with gr.Tabs():
                    with gr.Tab("Preview"):
                        preview = gr.Markdown(
                            "*Your brochure preview will appear here.*",
                            container=True,
                            min_height=420,
                        )
                    with gr.Tab("Edit"):
                        editor = gr.Textbox(
                            label="Brochure text (Markdown: # headings, - bullets, **bold**)",
                            placeholder="Generate a brochure first, then fix or fill in anything here.",
                            lines=18, max_lines=40,
                        )
                        update_btn = gr.Button("Update PDF & DOCX", variant="secondary")
                note = gr.Markdown(visible=False)
                with gr.Row():
                    pdf_file = gr.File(label="Download PDF")
                    docx_file = gr.File(label="Download DOCX")
                gr.Markdown("Fix or fill in anything in the **Edit** tab before downloading. "
                            "Changing the brand colour after generating re-colours the files instantly.")

        inputs = [company_name, website, audience, tone, fmt, length, language, sections, color]
        gr.Examples(examples=EXAMPLES, inputs=inputs, example_labels=EXAMPLE_LABELS,
                    label="Examples (click one, then Generate)")

        last_brochure = gr.State(None)
        outputs = [preview, pdf_file, docx_file, last_brochure, editor, note]
        gr.on([generate_btn.click, company_name.submit], generate, inputs=inputs, outputs=outputs,
              trigger_mode="once")
        editor.input(on_edit, inputs=editor, outputs=[preview, note], show_progress="hidden")
        # The editor's text is what gets exported, so edits survive a colour change too.
        # "change" (not "input") so typed hex codes and example clicks also recolour.
        reexport_args = {"fn": reexport, "inputs": [last_brochure, editor, color],
                         "outputs": [pdf_file, docx_file, note], "show_progress": "minimal"}
        update_btn.click(**reexport_args)
        color.change(trigger_mode="always_last", **reexport_args)

    return demo


def main():
    parser = argparse.ArgumentParser(description="AI Company Brochure Generator")
    parser.add_argument("--port", type=int, default=None, help="Port to run on (default: auto)")
    parser.add_argument("--share", action="store_true",
                        help="Also create a temporary public link (anyone with it can use your API key's quota)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    options = {"theme": gr.themes.Soft(), "allowed_paths": [str(OUTPUT_DIR)]}
    if HOSTED:  # Host and port come from GRADIO_SERVER_NAME / GRADIO_SERVER_PORT (set in the Dockerfile)
        build_ui().launch(**options)
    else:
        build_ui().launch(share=args.share, server_port=args.port, inbrowser=not args.no_browser, **options)


if __name__ == "__main__":
    main()
