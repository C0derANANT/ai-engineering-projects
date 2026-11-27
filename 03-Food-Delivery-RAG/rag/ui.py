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
    "Can I cancel my order after the restaurant starts cooking? Is there a fee?",
    "Mera order 40 minute late hai, kya mujhe kuch refund milega?",
    "मेरे ऑर्डर में एक आइटम नहीं आया, रिफंड कैसे मिलेगा?",
    "What do I get with CraveCart Plus, and how much does it cost?",
    "What does error CC-PAY-302 mean?",
    "How many sick leaves do employees get, and do they carry forward?",
]

HEADER = """
<div class="cc-header">
  <div class="cc-title">🍛 Crave Assist</div>
  <div class="cc-subtitle">
    RAG demo: ask about <b>CraveCart</b>, a fictional food delivery company. Answers come only from its
    18 help, policy and HR documents, with the sources shown. Ask in English, हिंदी or Hinglish.
  </div>
</div>
"""

ABOUT = """
### How it works
1. **Rewrite:** your question (and the chat so far) is turned into one clear English search query, so
   follow-ups like *"what if it was already cooking?"* and Hindi/Hinglish questions find the right documents.
2. **Retrieve:** the 5 closest passages come from a Chroma vector DB built from 18 Markdown documents,
   split at their headings (BGE embeddings).
3. **Answer:** Groq's `gpt-oss-120b` answers from those passages only, citing them as [1], [2]…, in the
   language you wrote in. If the documents don't cover something, it says so instead of guessing.

### What it knows
Company overview, fees and CraveCart Plus · ordering, tracking, delivery times, changing and cancelling
orders · cancellation and refund policies · payment and app FAQs · support procedures and error codes ·
HR policies (leave, benefits, onboarding, code of conduct).

It can't see real orders or accounts: ask how a policy works, not about a specific order.

<sub>CraveCart and its documents are fictional, written for a learning project.</sub>
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


def _quote(text: str, limit: int = 700) -> str:
    """A passage for the Sources panel: shortened, with its headings shown as bold text."""
    text = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"**\1**", text.strip())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return text


def sources_markdown(reply: Reply | None) -> str:
    """The right-hand 'Sources' panel for one answer."""
    if reply is None or not reply.hits:
        return EMPTY_SOURCES
    cited_numbers = reply.cited or parse_citations(reply.text, len(reply.hits))
    cited = [h for h in reply.hits if h.number in cited_numbers]
    others = [h for h in reply.hits if h.number not in cited_numbers]
    parts = []

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
