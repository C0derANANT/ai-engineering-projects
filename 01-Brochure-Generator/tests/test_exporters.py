"""Tests for brochure/exporters.py: links, placeholders, and PDF + DOCX smoke tests."""

import io
import re

import pytest
from docx import Document
from PIL import Image

from brochure import exporters
from brochure.exporters import (
    export_docx,
    export_pdf,
    find_placeholders,
    link_target,
    parse_inline,
    remove_placeholders,
)

SAMPLE = """# Acme Rockets: To Orbit and Back
*Reusable rockets for startups and researchers.*

## About Us
Acme builds **reusable rockets** and has flown _twelve_ missions. Read our story at
[acme.test/story](https://acme.test/story) or https://acme.test/press.

## Our Services & Products
- **Launch:** rides to low Earth orbit
  - Nested detail with AT&amp;T-grade \\*care\\*
1. Book a slot
2. Ship your payload

---

## Get in Touch
- **Website:** [acme.test](https://acme.test)
- **Email:** hello@acme.test
- **Phone:** [Phone]
- **Address:** [Address]

[Phone] – [Address]
"""


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    """Write exported files into a temporary folder instead of outputs/."""
    monkeypatch.setattr(exporters, "OUTPUT_DIR", tmp_path)
    return tmp_path


def logo_png(width=180, height=180) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), (245, 80, 54, 255)).save(buffer, "PNG")
    return buffer.getvalue()


def pdf_links(path) -> set[str]:
    return {m.decode() for m in re.findall(rb"/URI \((.*?)\)", path.read_bytes())}


def docx_links(document) -> set[str]:
    return {rel.target_ref for rel in document.part.rels.values() if "hyperlink" in rel.reltype}


# --------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------
def test_markdown_links_bare_urls_and_emails_become_links():
    runs = parse_inline("**Web:** [acme.test](https://acme.test), mail hello@acme.test or visit www.acme.test.")
    links = {text: link for text, _, _, link in runs if link}
    assert links == {
        "acme.test": "https://acme.test",
        "hello@acme.test": "mailto:hello@acme.test",
        "www.acme.test": "https://www.acme.test",  # the full stop after it is not part of the link
    }
    assert ("Web:", True, False, None) in runs


def test_link_keeps_its_bold_text():
    assert parse_inline("[**Acme** site](https://acme.test)")[0] == ("Acme", True, False, "https://acme.test")


def test_unsafe_and_relative_links_are_plain_text():
    runs = parse_inline("[click me](javascript:alert(1)) and [About](/about)")
    assert runs == [("click me and About", False, False, None)]


@pytest.mark.parametrize("text", [
    "Built with Node.js and ASP.NET", "e.g. version 2.0", "my_file_name", "see report.pdf", "acme.test",
])
def test_ordinary_words_are_not_links(text):
    assert all(link is None for *_, link in parse_inline(text))


@pytest.mark.parametrize("target, expected", [
    ("https://acme.test/a?b=1&amp;c=2", "https://acme.test/a?b=1&c=2"),
    ("mailto:hi@acme.test", "mailto:hi@acme.test"),
    ("tel:+911234567890", "tel:+911234567890"),
    ("hi@acme.test", "mailto:hi@acme.test"),
    ("acme.in", "https://acme.in"),
    ("javascript:alert(1)", None),
    ("file:///etc/passwd", None),
    ("/about", None),
])
def test_link_target(target, expected):
    assert link_target(target) == expected


# --------------------------------------------------------------------------
# Placeholders
# --------------------------------------------------------------------------
def test_find_placeholders_lists_each_once_and_ignores_links():
    assert find_placeholders(SAMPLE) == ["[Phone]", "[Address]"]


def test_placeholder_only_lines_are_dropped_and_real_details_kept():
    cleaned = remove_placeholders(SAMPLE)
    assert "[Phone]" not in cleaned and "[Address]" not in cleaned
    assert "- **Email:** hello@acme.test" in cleaned
    assert "- **Website:** [acme.test](https://acme.test)" in cleaned


@pytest.mark.parametrize("line, expected", [
    ("Email: hello@acme.test | Phone: [Phone]", "Email: hello@acme.test"),
    ("[Phone] | hello@acme.test | [Address]", "hello@acme.test"),
    ("Visit us at [Address]. We reply within a day.", "We reply within a day."),
    ("- फ़ोन: [फ़ोन]", None),            # translated placeholder (Hindi)
    ("**Teléfono:** [Teléfono]", None),  # translated placeholder (Spanish)
])
def test_placeholders_inside_lines(line, expected):
    cleaned = remove_placeholders(f"# Title\n## Contact\n{line}\nWe love to talk.")
    if expected is None:
        assert cleaned == "# Title\n## Contact\nWe love to talk."
    else:
        assert expected in cleaned.splitlines()


def test_heading_with_only_placeholders_is_dropped():
    markdown = "# Acme\n## About Us\nWe build rockets.\n## Get in Touch\n[Phone] – [Address]\n\n## FAQ\nQ?"
    assert remove_placeholders(markdown) == "# Acme\n## About Us\nWe build rockets.\n\n## FAQ\nQ?"


def test_brochure_without_placeholders_is_unchanged():
    markdown = "# Acme\n\n## About\n- Fast\n- Safe"
    assert remove_placeholders(markdown) == markdown


# --------------------------------------------------------------------------
# PDF and DOCX smoke tests
# --------------------------------------------------------------------------
def test_export_pdf(out_dir):
    path = export_pdf(SAMPLE, "Acme Rockets", color="#e11d48")
    assert path.parent == out_dir and path.suffix == ".pdf"
    data = path.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 1000
    assert pdf_links(path) == {
        "https://acme.test/story", "https://acme.test/press", "https://acme.test", "mailto:hello@acme.test",
    }
    assert b"/Subtype /Image" not in data  # no logo was given


def test_export_pdf_with_logo(out_dir):
    data = export_pdf(SAMPLE, "Acme Rockets", logo=logo_png()).read_bytes()
    assert b"/Subtype /Image" in data


def test_export_pdf_with_a_wide_logo_and_long_title(out_dir):
    title = "# " + "A very long headline that has to wrap over several lines " * 3
    export_pdf(title + SAMPLE, "Acme", logo=logo_png(300, 200))


def test_export_pdf_without_system_fonts(out_dir, monkeypatch):
    """With no Unicode font installed, the PDF falls back to Helvetica (Latin-1 only)."""
    monkeypatch.setattr(exporters, "_FONT_CANDIDATES", [])
    path = export_pdf("# Acme – “Rockets” for ₹100\n• Visit https://acme.test …", "Acme")
    assert path.read_bytes().startswith(b"%PDF")
    assert pdf_links(path) == {"https://acme.test"}


def test_export_pdf_in_hindi(out_dir):
    hindi = "# चाय पॉइंट\n## संपर्क करें\n- **ईमेल:** hello@chaipoint.com\n- फ़ोन: [फ़ोन]\n"
    assert export_pdf(hindi, "Chai Point", color="#2e7d32").read_bytes().startswith(b"%PDF")


def test_export_docx(out_dir):
    path = export_docx(SAMPLE, "Acme Rockets", color="#e11d48", logo=logo_png())
    assert path.parent == out_dir and path.suffix == ".docx"
    document = Document(str(path))
    paragraphs = [p for p in document.paragraphs if p.text.strip()]
    texts = [p.text for p in paragraphs]

    assert paragraphs[0].style.name == "Title"
    assert texts[0] == "Acme Rockets: To Orbit and Back"
    assert "Nested detail with AT&T-grade *care*" in texts
    assert "1.\tBook a slot" in texts
    assert "Email: hello@acme.test" in texts
    assert not any("[Phone]" in t or "[Address]" in t for t in texts)
    assert docx_links(document) == {
        "https://acme.test/story", "https://acme.test/press", "https://acme.test", "mailto:hello@acme.test",
    }
    assert len(document.inline_shapes) == 1  # the logo


def test_pdf_and_docx_can_share_a_basename(out_dir):
    basename = exporters.make_basename("Acme")
    pdf = export_pdf(SAMPLE, "Acme", basename)
    docx = export_docx(SAMPLE, "Acme", basename)
    assert pdf.stem == docx.stem == basename
