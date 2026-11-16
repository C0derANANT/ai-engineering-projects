"""Exports brochure Markdown to nicely formatted PDF and DOCX files."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
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

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+•]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
_INLINE = re.compile(r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|\*(?!\s).+?(?<!\s)\*)")


def parse_markdown(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush():
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph)))
            paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
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


def parse_inline(text: str) -> list[Run]:
    """Split text into runs of (text, bold, italic). Strips links and inline code."""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)  # [label](url) -> label
    text = text.replace("`", "")
    runs: list[Run] = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("***") and part.endswith("***") and len(part) > 6:
            runs.append((part[3:-3], True, True))
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            runs.append((part[2:-2], True, False))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            runs.append((part[1:-1], False, True))
        else:
            runs.append((part, False, False))
    return runs


def _output_path(company_name: str, ext: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-") or "company"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"{slug}-brochure-{stamp}.{ext}"


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
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]"
)
_LATIN1_FALLBACK = {
    "•": "-", "–": "-", "—": "-", "‑": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "₹": "Rs.", "€": "EUR", "™": "(TM)", "\u00a0": " ",
}


class BrochurePDF(FPDF):
    def __init__(self, company_name: str):
        super().__init__(format="A4")
        self.company_name = company_name
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(auto=True, margin=20)
        self.body_font = self._load_font()

    def _load_font(self) -> str:
        for regular, bold, italic, bold_italic in _FONT_CANDIDATES:
            if all(Path(p).exists() for p in (regular, bold, italic, bold_italic)):
                self.add_font("Body", "", regular)
                self.add_font("Body", "B", bold)
                self.add_font("Body", "I", italic)
                self.add_font("Body", "BI", bold_italic)
                self.has_unicode = True
                return "Body"
        self.has_unicode = False  # Core font: Latin-1 only
        return "Helvetica"

    def clean(self, text: str) -> str:
        text = _EMOJI.sub("", text)
        if self.has_unicode:
            # Swap symbols the TTF font can't draw (e.g. ₹ in Arial) for text equivalents
            glyphs = self.fonts["body"].cmap
            for char, repl in _LATIN1_FALLBACK.items():
                if char in text and ord(char) not in glyphs:
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


def export_pdf(markdown: str, company_name: str) -> Path:
    pdf = BrochurePDF(company_name)
    pdf.add_page()
    first_heading = True

    for block in parse_markdown(markdown):
        if block.kind == "heading" and (block.level == 1 or first_heading):
            # Title banner
            pdf.set_fill_color(*PRIMARY)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(pdf.body_font, "B", 20)
            pdf.multi_cell(0, 11, pdf.clean(block.text), fill=True, padding=(6, 6), align="L",
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)
            first_heading = False
        elif block.kind == "heading":
            if pdf.get_y() > pdf.h - 45:  # Keep heading with its content
                pdf.add_page()
            pdf.ln(3)
            size = 14 if block.level == 2 else 12
            pdf.set_font(pdf.body_font, "B", size)
            pdf.set_text_color(*(PRIMARY if block.level == 2 else ACCENT))
            pdf.multi_cell(0, 8, pdf.clean(block.text), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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

    path = _output_path(company_name, "pdf")
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


def export_docx(markdown: str, company_name: str) -> Path:
    doc = Document()
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
            style = "List Number" if block.level == 0 else f"List Number {block.level + 1}"
            _docx_add_runs(doc.add_paragraph(style=style), runs)
        elif block.kind == "rule":
            doc.add_paragraph()
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            _docx_add_runs(p, runs)

    path = _output_path(company_name, "docx")
    doc.save(str(path))
    return path
