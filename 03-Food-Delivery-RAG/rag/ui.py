"""Text and formatting for the Gradio app (kept apart from app.py so it can be tested)."""

from __future__ import annotations

import re

from .assistant import Reply, parse_citations

DOC_TYPE_ICONS = {
    "company": "🏢",
    "customer-faqs": "❓",
    "ordering": "🛵",
    "policies": "📜",
    "support": "🎧",
    "hr-policies": "👥",
}

EXAMPLES = [
    "I want to cancel order 1042. How much will I get back?",
    "Order 1045 mein Mutton Korma nahi aaya, kitna refund milega?",
    "मेरा ऑर्डर 1044 बहुत लेट है, क्या मुझे कुछ मिलेगा?",
    "How much would a ₹450 order from 6.5 km away cost with CraveCart Plus?",
    "What does error CC-PAY-302 mean?",
    "How many sick leaves do employees get, and do they carry forward?",
]

HEADER = """
<div class="cc-header">
  <div class="cc-title">🍛 Crave Assist</div>
  <div class="cc-subtitle">
    RAG help assistant for <b>CraveCart</b>, a fictional Zomato-style food delivery company.
    Answers cite their sources, order maths is exact, and it speaks English, हिंदी and Hinglish (type or 🎙️ speak).
  </div>
</div>
"""

ABOUT = """
### How it works
1. **Rewrite:** your question (and the chat so far) is turned into one clear English search query, so
   follow-ups like *"what if it was already cooking?"* and Hindi/Hinglish questions find the right documents.
2. **Retrieve:** the 5 closest passages come from a Chroma vector DB built from 18 policy and FAQ documents,
   split at their headings (BGE embeddings).
3. **Answer:** Groq's `gpt-oss-120b` writes the answer, citing passages as [1], [2]… For order questions it
   calls Python tools that apply the refund and cancellation policies exactly, so the ₹ figures are never guessed.
4. **Backup:** if Groq is rate-limited, Gemini takes over automatically.

### Try the demo orders
Orders **#1042–#1052** are made-up orders that each show a different policy case: grace period,
50% and 100% cancellation fees, very late orders, COD dues, missing items, scheduled orders and more.
They're a frozen snapshot, so the answers are the same every time.

<sub>CraveCart, its policies and its orders are fictional, written for a learning project.</sub>
"""

EMPTY_SOURCES = "_Ask a question and the passages behind the answer appear here, with the ones it cites marked ✅._"

CSS = """
.cc-header {padding: 6px 4px 2px}
.cc-title {font-size: 1.7rem; font-weight: 700}
.cc-subtitle {opacity: .8; margin-top: 2px}
#sources-panel details {margin: 2px 0 10px}
#sources-panel summary {cursor: pointer; opacity: .8}
footer {display: none !important}
"""


def split_message(message) -> tuple[str, list[str]]:
    """ChatInterface (multimodal) sends {'text': ..., 'files': [...]}; plain text is accepted too."""
    if isinstance(message, dict):
        files = []
        for f in message.get("files") or []:
            path = f.get("path") if isinstance(f, dict) else getattr(f, "path", f)
            if path:
                files.append(str(path))
        return (message.get("text") or "").strip(), files
    return str(message or "").strip(), []


def _quote(text: str, limit: int = 700) -> str:
    """A passage for the Sources panel: shortened, with its headings shown as bold text."""
    text = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"**\1**", text.strip())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return text


def sources_markdown(reply: Reply | None) -> str:
    """The right-hand 'Sources' panel for one answer."""
    if reply is None or (not reply.hits and not reply.tools_used):
        return EMPTY_SOURCES
    cited_numbers = reply.cited or parse_citations(reply.text, len(reply.hits))
    cited = [h for h in reply.hits if h.number in cited_numbers]
    others = [h for h in reply.hits if h.number not in cited_numbers]
    parts = []

    if reply.tools_used:
        parts.append("#### 🧮 Calculated with tools\n" + "\n".join(f"- `{t}`" for t in reply.tools_used))

    def block(hit, mark):
        icon = DOC_TYPE_ICONS.get(hit.doc_type, "📄")
        return (
            f"**[{hit.number}]** {mark} {icon} `{hit.source}`  \n"
            f"› {hit.section} · match {hit.score:.0%}\n"
            f"<details><summary>Show passage</summary>\n\n{_quote(hit.text)}\n\n</details>"
        )

    if cited:
        parts.append("#### 📚 Cited in the answer\n" + "\n\n".join(block(h, "✅") for h in cited))
    if others:
        title = "#### 🔎 Also retrieved" if cited else "#### 🔎 Retrieved passages"
        parts.append(title + "\n" + "\n\n".join(block(h, "") for h in others))

    meta = []
    if reply.query:
        meta.append(f"🔎 searched for: “{reply.query}”")
    if reply.model:
        meta.append(f"🤖 {reply.model}")
    if meta:
        parts.append("<sub>" + " · ".join(meta) + "</sub>")
    return "\n\n".join(parts)
