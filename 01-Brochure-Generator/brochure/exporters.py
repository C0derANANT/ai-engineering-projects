"""Exports brochure Markdown to nicely formatted PDF and DOCX files."""

import html
import importlib.util
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .config import OUTPUT_DIR

# Brand colours (RGB)
PRIMARY = (30, 58, 138)    # deep blue
ACCENT = (37, 99, 235)     # bright blue
TEXT = (31, 41, 55)        # dark grey
MUTED = (107, 114, 128)    # light grey


# --------------------------------------------------------------------------
# Markdown parsing (shared by PDF and DOCX)
# --------------------------------------------------------------------------
@dataclass
class Block:
    kind: str          # "heading" | "bullet" | "number" | "paragraph" | "rule"
    text: str = ""
    level: int = 0     # heading level, or list nesting depth
    marker: str = ""   # "1." for numbered lists


Run = tuple[str, bool, bool]  # (text, bold, italic)

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # Word refuses these
_QUOTE = re.compile(r"^\s*(>\s?)+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+•]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
_INLINE = re.compile(
    r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|__.+?__|\*(?!\s).+?(?<!\s)\*|(?<!\w)_(?!\s).+?(?<!\s)_(?!\w))"
)
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!&|>~])")
# Escaped * and _ are parked on private-use characters so they aren't read as formatting
_PARKED = {"*": "\ue000", "_": "\ue001"}


def parse_markdown(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush():
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph)))
            paragraph.clear()

    for raw in _CONTROL.sub("", markdown).splitlines():
        line = _QUOTE.sub("", raw.rstrip())  # "> quote" -> plain text
        if not line.strip() or line.strip().startswith("```"):
            flush()
            continue
        if _RULE.match(line):
            flush()
            blocks.append(Block("rule"))
        elif m := _HEADING.match(line.strip()):
            flush()
            blocks.append(Block("heading", m.group(2).strip("# "), len(m.group(1))))
        elif m := _BULLET.match(line):
            flush()
            blocks.append(Block("bullet", m.group(2), min(len(m.group(1)) // 2, 2)))
        elif m := _NUMBER.match(line):
            flush()
            blocks.append(Block("number", m.group(3), min(len(m.group(1)) // 2, 2), f"{m.group(2)}."))
        elif line.lstrip().startswith("|"):
            flush()
            if not _TABLE_SEPARATOR.match(line):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                blocks.append(Block("paragraph", "  |  ".join(c for c in cells if c)))
        else:
            paragraph.append(line.strip())
    flush()
    return blocks


def _link_text(m: re.Match) -> str:
    label, target = m.group(1).strip(), re.sub(r"^(mailto|tel):", "", m.group(2))
    bare = re.sub(r"^https?://(www\.)?", "", target).rstrip("/").lower()
    return label if bare in label.lower() else f"{label} ({target})"


def parse_inline(text: str) -> list[Run]:
    """Split text into runs of (text, bold, italic). Handles **bold**, *italic*,
    __bold__, _italic_, links, `code`, backslash escapes and HTML entities."""
    text = _LINK.sub(_link_text, text)
    text = text.replace("`", "").replace("~~", "")
    text = _ESCAPED.sub(lambda m: _PARKED.get(m.group(1), m.group(1)), text)
    text = html.unescape(text)

    def unpark(s: str) -> str:
        return s.replace(_PARKED["*"], "*").replace(_PARKED["_"], "_")

    runs: list[Run] = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("***") and part.endswith("***") and len(part) > 6:
            runs.append((unpark(part[3:-3]), True, True))
        elif part[:2] in ("**", "__") and part[-2:] == part[:2] and len(part) > 4:
            runs.append((unpark(part[2:-2]), True, False))
        elif part[0] in "*_" and part[-1] == part[0] and len(part) > 2:
            runs.append((unpark(part[1:-1]), False, True))
        else:
            runs.append((unpark(part), False, False))
    return runs


def plain_text(text: str) -> str:
    """Inline Markdown with the formatting marks removed (for headings)."""
    return "".join(t for t, _, _ in parse_inline(text))


# --------------------------------------------------------------------------
# File names
# --------------------------------------------------------------------------
def make_basename(company_name: str) -> str:
    """A unique, filesystem-safe base name like 'acme-brochure-20261118-101500-a3f9'.

    The random suffix stops two brochures made in the same second (or by two
    people using the share link) from overwriting each other.
    """
    ascii_name = unicodedata.normalize("NFKD", company_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:50].strip("-") or "company"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    while True:
        name = f"{slug}-brochure-{stamp}-{secrets.token_hex(3)}"
        if not any(OUTPUT_DIR.glob(f"{name}.*")):
            return name


def _output_path(company_name: str, ext: str, basename: str | None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"{basename or make_basename(company_name)}.{ext}"


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
# Unicode TTF fonts (regular, bold, italic, bold-italic) by OS; first match wins
_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
     "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/arialbi.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
]
# Extra fonts for scripts Arial/DejaVu lack (Hindi, Chinese, Japanese, Korean, ...).
# Only loaded when the brochure actually contains such characters.
_FALLBACK_FONTS = [
    "/System/Library/Fonts/Kohinoor.ttc",                       # macOS: Devanagari, ₹
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",     # macOS: CJK, Indic, Thai...
    "C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/Nirmala.ttf",  # Windows: Indic
    "C:/Windows/Fonts/msyh.ttc",                                # Windows: Chinese
    "C:/Windows/Fonts/YuGothR.ttc",                             # Windows: Japanese
    "C:/Windows/Fonts/malgun.ttf",                              # Windows: Korean
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",  # Linux (fonts-noto)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
]
# Scripts that need a shaping engine to join letters / reorder vowels correctly
_COMPLEX_SCRIPT = re.compile("[\u0590-\u08ff\u0900-\u0dff\u0e00-\u0eff\u0f00-\u109f\u1780-\u17ff\ufb1d-\ufdff\ufe70-\ufeff]")
_HAS_SHAPER = importlib.util.find_spec("uharfbuzz") is not None
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]"
)
_LATIN1_FALLBACK = {
    "•": "-", "–": "-", "—": "-", "‑": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "₹": "Rs.", "€": "EUR", "™": "(TM)", "\u00a0": " ",
}


class BrochurePDF(FPDF):
    def __init__(self, company_name: str, sample_text: str = ""):
        super().__init__(format="A4")
        self.company_name = company_name
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(auto=True, margin=20)
        self.set_title(f"{company_name} brochure")
        self.cmaps: list[dict] = []
        self.body_font = self._load_font(sample_text + company_name)

    def _load_font(self, sample_text: str) -> str:
        for regular, bold, italic, bold_italic in _FONT_CANDIDATES:
            if all(Path(p).exists() for p in (regular, bold, italic, bold_italic)):
                self.add_font("Body", "", regular)
                self.add_font("Body", "B", bold)
                self.add_font("Body", "I", italic)
                self.add_font("Body", "BI", bold_italic)
                self.has_unicode = True
                self.cmaps.append(self.fonts["body"].cmap)
                self._add_fallbacks(sample_text)
                return "Body"
        self.has_unicode = False  # Core font: Latin-1 only
        return "Helvetica"

    def _add_fallbacks(self, text: str) -> None:
        text = _EMOJI.sub("", text)
        missing = {c for c in text if not c.isspace() and ord(c) not in self.cmaps[0]}
        if missing:
            names = []
            for i, path in enumerate(p for p in _FALLBACK_FONTS if Path(p).exists()):
                name = f"Fallback{i}"
                self.add_font(name, "", path)
                self.cmaps.append(self.fonts[name.lower()].cmap)
                names.append(name)
            if names:
                self.set_fallback_fonts(names, exact_match=False)
        if _HAS_SHAPER and _COMPLEX_SCRIPT.search(text):
            self.set_text_shaping(True)  # joins Arabic letters, places Hindi vowel signs

    def _has_glyph(self, char: str) -> bool:
        return any(ord(char) in cmap for cmap in self.cmaps)

    def clean(self, text: str) -> str:
        text = _EMOJI.sub("", text)
        if self.has_unicode:
            # Swap symbols no loaded font can draw (e.g. ₹ in plain Arial) for text equivalents
            for char, repl in _LATIN1_FALLBACK.items():
                if char in text and not self._has_glyph(char):
                    text = text.replace(char, repl)
        else:
            for char, repl in _LATIN1_FALLBACK.items():
                text = text.replace(char, repl)
            text = text.encode("latin-1", "replace").decode("latin-1")
        return text

    def header(self):
        if self.page_no() > 1:
            self.set_font(self.body_font, "B", 9)
            self.set_text_color(*MUTED)
            self.cell(0, 6, self.clean(self.company_name), align="R",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*ACCENT)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_font(self.body_font, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")


def _pdf_write_runs(pdf: BrochurePDF, runs: list[Run], size: float, line_h: float):
    for text, bold, italic in runs:
        style = ("B" if bold else "") + ("I" if italic else "")
        pdf.set_font(pdf.body_font, style, size)
        pdf.write(line_h, pdf.clean(text))
    pdf.ln(line_h)


def export_pdf(markdown: str, company_name: str, basename: str | None = None) -> Path:
    pdf = BrochurePDF(company_name, sample_text=markdown)
    pdf.add_page()
    first_heading = True

    for block in parse_markdown(markdown):
        if block.kind == "heading" and (block.level == 1 or first_heading):
            # Title banner
            pdf.set_fill_color(*PRIMARY)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(pdf.body_font, "B", 20)
            pdf.multi_cell(0, 11, pdf.clean(plain_text(block.text)), fill=True, padding=(6, 6),
                           align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)
            first_heading = False
        elif block.kind == "heading":
            if pdf.get_y() > pdf.h - 45:  # Keep heading with its content
                pdf.add_page()
            pdf.ln(3)
            size = 14 if block.level == 2 else 12
            pdf.set_font(pdf.body_font, "B", size)
            pdf.set_text_color(*(PRIMARY if block.level == 2 else ACCENT))
            pdf.multi_cell(0, 8, pdf.clean(plain_text(block.text)), align="L",
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if block.level == 2:
                pdf.set_draw_color(*ACCENT)
                pdf.set_line_width(0.4)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 30, pdf.get_y())
                pdf.set_line_width(0.2)
            pdf.ln(2)
        elif block.kind in ("bullet", "number"):
            pdf.set_text_color(*TEXT)
            base = pdf.l_margin
            indent = 4 + block.level * 6
            marker = "•" if block.kind == "bullet" and pdf.has_unicode else (block.marker or "-")
            pdf.set_x(base + indent)
            pdf.set_font(pdf.body_font, "B", 11)
            pdf.set_text_color(*ACCENT)
            pdf.write(6, marker)
            pdf.set_text_color(*TEXT)
            pdf.set_left_margin(base + indent + 6)
            pdf.set_x(base + indent + 6)
            _pdf_write_runs(pdf, parse_inline(block.text), 11, 6)
            pdf.set_left_margin(base)
            pdf.ln(1)
        elif block.kind == "rule":
            pdf.ln(2)
            pdf.set_draw_color(*MUTED)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(4)
        else:  # paragraph
            pdf.set_text_color(*TEXT)
            _pdf_write_runs(pdf, parse_inline(block.text), 11, 6)
            pdf.ln(3)

    path = _output_path(company_name, "pdf", basename)
    pdf.output(str(path))
    return path


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------
def _docx_add_runs(paragraph, runs: list[Run]):
    for text, bold, italic in runs:
        run = paragraph.add_run(text)
        run.bold = bold or None
        run.italic = italic or None


def export_docx(markdown: str, company_name: str, basename: str | None = None) -> Path:
    doc = Document()
    doc.core_properties.title = f"{company_name} brochure"
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for name, size in (("Title", 26), ("Heading 1", 18), ("Heading 2", 15), ("Heading 3", 13)):
        style = doc.styles[name]
        style.font.color.rgb = RGBColor(*PRIMARY)
        style.font.size = Pt(size)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.text = f"{company_name} | Company Brochure"
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    first_heading = True
    for block in parse_markdown(markdown):
        runs = parse_inline(block.text)
        if block.kind == "heading":
            if block.level == 1 or first_heading:
                p = doc.add_paragraph(style="Title")
                first_heading = False
            else:
                p = doc.add_heading(level=min(block.level - 1, 3))
            _docx_add_runs(p, [(t, False, i) for t, _, i in runs])
        elif block.kind == "bullet":
            style = "List Bullet" if block.level == 0 else f"List Bullet {block.level + 1}"
            _docx_add_runs(doc.add_paragraph(style=style), runs)
        elif block.kind == "number":
            # Word's "List Number" style keeps counting across separate lists (a second
            # list would start at 4), so write the brochure's own number instead.
            p = doc.add_paragraph()
            indent = Cm(0.75 + 0.75 * block.level)
            p.paragraph_format.left_indent = indent
            p.paragraph_format.first_line_indent = Cm(-0.75)
            p.paragraph_format.tab_stops.add_tab_stop(indent)
            p.paragraph_format.space_after = Pt(4)
            p.add_run(f"{block.marker}\t")
            _docx_add_runs(p, runs)
        elif block.kind == "rule":
            doc.add_paragraph()
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            _docx_add_runs(p, runs)

    path = _output_path(company_name, "docx", basename)
    doc.save(str(path))
    return path
