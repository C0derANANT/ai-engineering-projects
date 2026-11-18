"""Exports brochure Markdown to nicely formatted PDF and DOCX files."""

import colorsys
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
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .config import OUTPUT_DIR

RGB = tuple[int, int, int]

# Default brand colours
PRIMARY = (30, 58, 138)    # deep blue
ACCENT = (37, 99, 235)     # bright blue
TEXT = (31, 41, 55)        # dark grey
MUTED = (107, 114, 128)    # light grey
WHITE = (255, 255, 255)
DEFAULT_COLOR = "#1e3a8a"  # PRIMARY as hex, the colour picker's starting value


# --------------------------------------------------------------------------
# Brand colour -> readable palette
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Palette:
    primary: RGB = PRIMARY   # title banner fill
    on_primary: RGB = WHITE  # text on the title banner
    heading: RGB = PRIMARY   # section headings (always readable on white)
    accent: RGB = ACCENT     # bullets, rules, sub-headings


def parse_color(value: str | None) -> RGB | None:
    """Accept '#1e3a8a', '#abc', 'rgb(30, 58, 138)' or 'rgba(...)'; None if invalid."""
    value = (value or "").strip().lower()
    if m := re.fullmatch(r"#?([0-9a-f]{6}|[0-9a-f]{3})", value):
        digits = m.group(1)
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    if m := re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(,\s*[\d.]+\s*)?\)", value):
        return tuple(max(0, min(255, round(float(m.group(i))))) for i in (1, 2, 3))
    return None


def _luminance(rgb: RGB) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: RGB, b: RGB) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _with_lightness(rgb: RGB, lightness: float) -> RGB:
    h, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), s))


def _readable_on_white(rgb: RGB) -> RGB:
    """Darken a colour until text in it is readable on white (WCAG 4.5:1)."""
    lightness = colorsys.rgb_to_hls(*(c / 255 for c in rgb))[1]
    while _contrast(rgb, WHITE) < 4.5 and lightness > 0:
        lightness -= 0.03
        rgb = _with_lightness(rgb, lightness)
    return rgb


def make_palette(color: str | None) -> Palette:
    """Build the brochure colours from one brand colour, keeping all text readable."""
    primary = parse_color(color)
    if primary is None or primary == PRIMARY:
        return Palette()
    on_primary = WHITE if _contrast(primary, WHITE) >= _contrast(primary, TEXT) else TEXT
    heading = _readable_on_white(primary)
    lightness = colorsys.rgb_to_hls(*(c / 255 for c in heading))[1]
    accent = _readable_on_white(_with_lightness(heading, lightness + 0.12))
    return Palette(primary=primary, on_primary=on_primary, heading=heading, accent=accent)


# --------------------------------------------------------------------------
# Markdown parsing (shared by PDF and DOCX)
# --------------------------------------------------------------------------
@dataclass
class Block:
    kind: str          # "heading" | "bullet" | "number" | "paragraph" | "rule"
    text: str = ""
    level: int = 0     # heading level, or list nesting depth
    marker: str = ""   # "1." for numbered lists


Run = tuple[str, bool, bool, str | None]  # (text, bold, italic, link URL or None)

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
_ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!&|>~])")
# Escaped * and _ are parked on private-use characters so they aren't read as formatting
_PARKED = {"*": "\ue000", "_": "\ue001"}

# Links. A Markdown link [label](url) and anything that looks like a web address or
# email in plain text become clickable. Plain domains only count with a common
# ending (.com, .ai, .in ...) in lower case, so "Node.js" or "ASP.NET" stay text.
_LINK_MD = r"\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+\"[^\"]*\")?\)"
_URL = r"https?://[^\s<>()\[\]\"'`*]+"
_EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
_TLDS = ("com|org|net|io|ai|co|in|dev|app|tech|edu|gov|info|biz|me|us|uk|de|fr|es|it|nl"
         "|jp|cn|kr|au|ca|xyz|store|shop|cloud")
_DOMAIN = rf"(?:[A-Za-z0-9-]+\.)+(?:{_TLDS})(?![\w@-])(?:/[^\s<>()\[\]\"'`*]*)?"
_AUTOLINK = re.compile(
    rf"{_LINK_MD}|(?P<url>{_URL})|(?P<email>(?<![\w.%+-]){_EMAIL})|(?P<domain>(?<![\w@./:-]){_DOMAIN})"
)
_TRAILING = ".,;:!?_"           # sentence punctuation after an address is not part of it
_LINK_OPEN, _LINK_CLOSE = "\ue002", "\ue003"  # wrap linked text while bold/italic is parsed
_LINK_SPLIT = re.compile(f"({_LINK_OPEN}|{_LINK_CLOSE})")


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


def _park(text: str) -> str:
    """Hide * and _ so an address like my_page_name isn't read as italics."""
    return text.replace("*", _PARKED["*"]).replace("_", _PARKED["_"])


def link_target(target: str) -> str | None:
    """The URL a link should open, or None if it isn't safe to make clickable.

    Only web, email and phone links are allowed: the text comes from an AI, so a
    `javascript:` or `file:` link must never end up clickable in the brochure.
    """
    target = html.unescape(target.strip())
    if re.match(r"(?i)(https?://|mailto:|tel:)", target):
        return target
    if re.fullmatch(_EMAIL, target):
        return f"mailto:{target}"
    if re.fullmatch(_DOMAIN, target):
        return f"https://{target}"
    return None


def _mark_links(text: str, links: list[str]) -> str:
    """Wrap every link in markers and collect its URL, in order, into `links`."""
    def replace(m: re.Match) -> str:
        if m.group(1) is not None:  # [label](url)
            label, target = m.group(1).strip(), m.group(2)
            url = link_target(target)
            if url is None:  # a relative or unsafe link: keep just the words
                return label
            # Show the address after the label too ("our team (hi@acme.com)") so it
            # still helps in a printed copy, unless the label already says it
            shown = re.sub(r"^(mailto|tel):", "", target)
            bare = re.sub(r"^https?://(www\.)?", "", shown).rstrip("/").lower()
            same_phone = url.startswith("tel:") and re.sub(r"\D", "", label) == re.sub(r"\D", "", shown)
            visible = label if bare in label.lower() or same_phone else f"{label} ({_park(shown)})"
        else:  # a bare address; sentence punctuation right after it stays outside the link
            address = m.group(0).rstrip(_TRAILING)
            url = link_target(address)
            if url is None:
                return m.group(0)
            links.append(url)
            return f"{_LINK_OPEN}{_park(address)}{_LINK_CLOSE}{m.group(0)[len(address):]}"
        links.append(url)
        return f"{_LINK_OPEN}{visible}{_LINK_CLOSE}"

    return _AUTOLINK.sub(replace, text)


def parse_inline(text: str) -> list[Run]:
    """Split text into runs of (text, bold, italic, link). Handles **bold**, *italic*,
    __bold__, _italic_, links, bare URLs and emails, `code`, backslash escapes and
    HTML entities."""
    links: list[str] = []
    text = _mark_links(text, links)
    text = text.replace("`", "").replace("~~", "")
    text = _ESCAPED.sub(lambda m: _PARKED.get(m.group(1), m.group(1)), text)
    text = html.unescape(text)

    def unpark(s: str) -> str:
        return s.replace(_PARKED["*"], "*").replace(_PARKED["_"], "_")

    styled: list[tuple[str, bool, bool]] = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("***") and part.endswith("***") and len(part) > 6:
            styled.append((part[3:-3], True, True))
        elif part[:2] in ("**", "__") and part[-2:] == part[:2] and len(part) > 4:
            styled.append((part[2:-2], True, False))
        elif part[0] in "*_" and part[-1] == part[0] and len(part) > 2:
            styled.append((part[1:-1], False, True))
        else:
            styled.append((part, False, False))

    # Give each piece of text the link it sits inside (a link can span bold and plain text)
    runs: list[Run] = []
    next_link, current = iter(links), None
    for part, bold, italic in styled:
        for piece in _LINK_SPLIT.split(part):
            if piece == _LINK_OPEN:
                current = next(next_link, None)
            elif piece == _LINK_CLOSE:
                current = None
            elif piece:
                runs.append((unpark(piece), bold, italic, current))
    return runs


def plain_text(text: str) -> str:
    """Inline Markdown with the formatting marks removed (for headings)."""
    return "".join(run[0] for run in parse_inline(text))


# --------------------------------------------------------------------------
# Placeholders
# --------------------------------------------------------------------------
# The AI writes [Phone], [Email], [Address] (or translated ones like [Teléfono]) for
# details the website didn't give, instead of inventing them. They show in the editable
# preview so the user can fill them in; whatever is left is kept out of the PDF and DOCX.
_PLACEHOLDER = re.compile(r"\[[^\[\]()]{1,40}\](?!\()")  # [Phone], but not a [link](url)
_PART_SEPARATOR = re.compile(r"(\s+(?:\||–|—|-|·|•|/)\s+)")  # "Email: a@b.com | Phone: [Phone]"
_SENTENCE_END = re.compile(r"(?<=[.!?।。！？])\s+")
_LABEL = re.compile(r"^[^:\[\]]{1,30}:")  # "Phone:" / "फ़ोन:" at the start of a part
_LINE_PREFIX = re.compile(r"^\s*(?:>\s*)*(?:[-*+•]\s+|\d+[.)]\s+)?")  # "> ", "- ", "2. "


def find_placeholders(markdown: str) -> list[str]:
    """Placeholders still in the brochure, in order, without repeats: ['[Phone]', ...]."""
    found = _PLACEHOLDER.findall(markdown or "")
    return list(dict.fromkeys(found))


def _only_placeholders(text: str) -> bool:
    """True for text like "[Phone]", "**Phone:** [Phone]" or "[Phone] – [Address]"."""
    rest = re.sub(r"[*_`]", "", _PLACEHOLDER.sub("", text)).strip()
    rest = _LABEL.sub("", rest)
    return not re.search(r"\w", rest)


def _strip_placeholders(text: str) -> str:
    """One line without its unfilled placeholders; '' if nothing real is left.

    "Email: a@b.com | Phone: [Phone]" keeps the email part, and in running text
    only the sentence with the placeholder goes ("Visit us at [Address].").
    """
    pieces = _PART_SEPARATOR.split(text)  # [part, separator, part, separator, part]
    kept = ""
    for i in range(0, len(pieces), 2):
        part = pieces[i]
        if _PLACEHOLDER.search(part) and not _only_placeholders(part):
            part = " ".join(s for s in _SENTENCE_END.split(part) if not _PLACEHOLDER.search(s))
        if not part.strip() or _only_placeholders(part):
            continue
        kept += (pieces[i - 1] if kept else "") + part
    return kept.strip()


def _heading_level(line: str | None) -> int:
    m = _HEADING.match(line.strip()) if line else None
    return len(m.group(1)) if m else 0


def remove_placeholders(markdown: str) -> str:
    """The brochure without unfilled placeholders, ready to export.

    Works line by line (before lines are joined into paragraphs), so a real
    email on one line is never lost because the next line says [Phone]. A
    heading left with nothing under it, like "Get in Touch", is dropped too.
    """
    lines: list[str | None] = []  # None = a line that held only placeholders
    for line in (markdown or "").splitlines():
        if not _PLACEHOLDER.search(line) or _heading_level(line):
            lines.append(line)
            continue
        prefix = _LINE_PREFIX.match(line).group(0)  # keep the bullet or number
        text = _strip_placeholders(line[len(prefix):])
        lines.append(prefix + text if text else None)

    result: list[str] = []
    seen_title = False
    for i, line in enumerate(lines):
        if line is None:
            continue
        level = _heading_level(line)
        if level and seen_title:
            section = []
            for later in lines[i + 1:]:
                if 0 < _heading_level(later) <= level:
                    break
                if later is None or (later.strip() and not _RULE.match(later)):
                    section.append(later)
            if section and all(later is None for later in section):
                continue  # every line under this heading was a placeholder
        seen_title = seen_title or bool(level)
        result.append(line)
    return "\n".join(result)


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
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",    # Linux: fonts-noto-core
     "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
     "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf",
     "/usr/share/fonts/truetype/noto/NotoSans-BoldItalic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
]
# Extra fonts for scripts Arial/DejaVu lack (Hindi, Chinese, Japanese, Korean, ...).
# Only loaded when the brochure actually contains such characters.
# Each entry: (regular file, index in .ttc, bold file or None, bold index)
_FALLBACK_FONTS = [
    # macOS
    ("/System/Library/Fonts/Kohinoor.ttc", 0, "/System/Library/Fonts/Kohinoor.ttc", 2),  # Devanagari, ₹
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0, None, 0),  # CJK, Korean, other Indic
    # Windows
    ("C:/Windows/Fonts/Nirmala.ttf", 0, "C:/Windows/Fonts/NirmalaB.ttf", 0),  # Indic (Windows 10)
    ("C:/Windows/Fonts/Nirmala.ttc", 0, "C:/Windows/Fonts/NirmalaB.ttc", 0),  # Indic (Windows 11)
    ("C:/Windows/Fonts/msyh.ttc", 0, "C:/Windows/Fonts/msyhbd.ttc", 0),      # Chinese
    ("C:/Windows/Fonts/YuGothR.ttc", 0, "C:/Windows/Fonts/YuGothB.ttc", 0),  # Japanese
    ("C:/Windows/Fonts/malgun.ttf", 0, "C:/Windows/Fonts/malgunbd.ttf", 0),  # Korean
    # Linux (apt install fonts-noto-core fonts-noto-cjk)
    ("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", 0,
     "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0,
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
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
    def __init__(self, company_name: str, sample_text: str = "", palette: Palette | None = None):
        super().__init__(format="A4")
        self.company_name = company_name
        self.palette = palette or Palette()
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(auto=True, margin=20)
        self.set_title(f"{company_name} brochure")
        self.cmaps: list[dict] = []
        self.body_font = self._load_font(sample_text + company_name)

    def _load_font(self, sample_text: str) -> str:
        for regular, bold, italic, bold_italic in _FONT_CANDIDATES:
            if Path(regular).exists() and Path(bold).exists():
                # Italic files are optional (Debian's fonts-dejavu-core has none): fall back to upright
                self.add_font("Body", "", regular)
                self.add_font("Body", "B", bold)
                self.add_font("Body", "I", italic if Path(italic).exists() else regular)
                self.add_font("Body", "BI", bold_italic if Path(bold_italic).exists() else bold)
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
            for regular, index, bold, bold_index in _FALLBACK_FONTS:
                if not Path(regular).exists():
                    continue
                name = f"Fallback{len(names)}"
                self.add_font(name, "", regular, collection_font_number=index)
                if bold and Path(bold).exists():
                    self.add_font(name, "B", bold, collection_font_number=bold_index)
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
        self.set_draw_color(*self.palette.accent)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_font(self.body_font, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")


def _pdf_write_runs(pdf: BrochurePDF, runs: list[Run], size: float, line_h: float):
    after_space = False
    for text, bold, italic, link in runs:
        text = pdf.clean(text)
        # Links are underlined in the accent colour, and clicking them opens the URL
        style = ("B" if bold else "") + ("I" if italic else "") + ("U" if link else "")
        pdf.set_font(pdf.body_font, style, size)
        pdf.set_text_color(*(pdf.palette.accent if link else TEXT))
        # write() only wraps at spaces inside its own text, so a long first word (like a
        # URL right after "visit ") would be cut in half. Start a new line for it instead.
        first_word = text.split(" ", 1)[0]
        if after_space and first_word:
            room = pdf.w - pdf.r_margin - pdf.get_x()
            if room < pdf.get_string_width(first_word) <= pdf.w - pdf.r_margin - pdf.l_margin:
                pdf.ln(line_h)
        pdf.write(line_h, text, link=link or "")
        after_space = text[-1:].isspace()
    pdf.set_text_color(*TEXT)
    pdf.ln(line_h)


def export_pdf(markdown: str, company_name: str, basename: str | None = None,
               color: str | None = None) -> Path:
    """Write the brochure as an A4 PDF. `color` is the brand colour, e.g. '#e11d48'."""
    colors = make_palette(color)
    pdf = BrochurePDF(company_name, sample_text=markdown, palette=colors)
    pdf.add_page()
    first_heading = True

    for block in parse_markdown(remove_placeholders(markdown)):
        if block.kind == "heading" and (block.level == 1 or first_heading):
            # Title banner
            pdf.set_fill_color(*colors.primary)
            pdf.set_text_color(*colors.on_primary)
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
            pdf.set_text_color(*(colors.heading if block.level == 2 else colors.accent))
            pdf.multi_cell(0, 8, pdf.clean(plain_text(block.text)), align="L",
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if block.level == 2:
                pdf.set_draw_color(*colors.accent)
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
            pdf.set_text_color(*colors.accent)
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
def _docx_add_runs(paragraph, runs: list[Run], link_color: RGB = ACCENT):
    for text, bold, italic, link in runs:
        run = paragraph.add_run(text)
        run.bold = bold or None
        run.italic = italic or None
        if link:
            _docx_make_hyperlink(paragraph, run, link, link_color)


def _docx_make_hyperlink(paragraph, run, url: str, color: RGB) -> None:
    """Turn a run into a clickable link. python-docx has no API for this, so we
    wrap the run in a <w:hyperlink> element that points at the URL."""
    run.font.underline = True
    run.font.color.rgb = RGBColor(*color)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run._r.addprevious(hyperlink)
    hyperlink.append(run._r)


def export_docx(markdown: str, company_name: str, basename: str | None = None,
                color: str | None = None) -> Path:
    """Write the brochure as a Word file. `color` is the brand colour, e.g. '#e11d48'."""
    colors = make_palette(color)
    doc = Document()
    doc.core_properties.title = f"{company_name} brochure"
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for name, size, rgb in (("Title", 26, colors.heading), ("Heading 1", 18, colors.heading),
                            ("Heading 2", 15, colors.accent), ("Heading 3", 13, colors.accent)):
        style = doc.styles[name]
        style.font.color.rgb = RGBColor(*rgb)
        style.font.size = Pt(size)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.text = f"{company_name} | Company Brochure"
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    first_heading = True
    for block in parse_markdown(remove_placeholders(markdown)):
        runs = parse_inline(block.text)
        if block.kind == "heading":
            if block.level == 1 or first_heading:
                p = doc.add_paragraph(style="Title")
                first_heading = False
            else:
                p = doc.add_heading(level=min(block.level - 1, 3))
            _docx_add_runs(p, [(t, False, i, None) for t, _, i, _ in runs])  # headings: no links
        elif block.kind == "bullet":
            style = "List Bullet" if block.level == 0 else f"List Bullet {block.level + 1}"
            _docx_add_runs(doc.add_paragraph(style=style), runs, colors.accent)
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
            _docx_add_runs(p, runs, colors.accent)
        elif block.kind == "rule":
            doc.add_paragraph()
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            _docx_add_runs(p, runs, colors.accent)

    path = _output_path(company_name, "docx", basename)
    doc.save(str(path))
    return path
