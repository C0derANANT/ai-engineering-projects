"""Movie facts from English Wikipedia (free, no API key).

- search_films: film articles matching a title or description (only pages with a film infobox)
- get_film: the infobox facts (director, cast, budget, box office ...), the opening summary
  and the list of sections, for one film
- get_section: the text of one section (Plot, Cast, Box office, Reception ...)

Results are cached in memory, so follow-up questions about the same film are instant.
"""

from __future__ import annotations

import logging
import re
from difflib import get_close_matches
from functools import lru_cache
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"
# Wikimedia asks API clients to identify themselves with a descriptive User-Agent
USER_AGENT = "AIMovieChatbot/2.0 (https://github.com/C0derANANT/ai-engineering-projects; educational demo)"
TIMEOUT = (5, 15)  # seconds to connect, seconds to wait for data
FILM_FILTER = 'hastemplate:"Infobox film"'

MAX_SUMMARY_CHARS = 1500  # most of the lead, which usually says how the film did commercially
MAX_SECTION_CHARS = 2500
MAX_FACT_CHARS = 250

# Infobox rows worth passing to the model, in this order (other rows are ignored)
FACT_LABELS = [
    "Directed by", "Written by", "Screenplay by", "Story by", "Dialogues by", "Based on", "Produced by",
    "Starring", "Narrated by", "Cinematography", "Edited by", "Music by", "Production company",
    "Production companies", "Distributed by", "Release date", "Release dates", "Running time", "Country",
    "Countries", "Language", "Languages", "Budget", "Box office",
]


class WikipediaError(Exception):
    """Wikipedia couldn't be reached or didn't have the page. The message is for the user."""


# -----------------------------------------------------------------------------------------
# HTTP
# -----------------------------------------------------------------------------------------
def _api(params: dict) -> dict:
    """Call the MediaWiki API and return its JSON (tests replace this function)."""
    try:
        response = requests.get(
            API_URL,
            params={**params, "format": "json", "formatversion": 2},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout as exc:
        raise WikipediaError("Wikipedia took too long to answer") from exc
    except requests.RequestException as exc:
        raise WikipediaError("Wikipedia couldn't be reached") from exc
    except ValueError as exc:  # not JSON
        raise WikipediaError("Wikipedia sent an unexpected reply") from exc


def page_url(title: str, anchor: str = "") -> str:
    url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="():,'_-.!")
    return url + ("#" + quote(anchor.replace(" ", "_"), safe="_-.") if anchor else "")


def _clean_html_text(node) -> str:
    """Readable text from a piece of Wikipedia HTML: no [1] references, hidden spans or edit links."""
    for junk in node.select(
        "sup.reference, sup.noprint, .noprint, .mw-editsection, style, script, "
        ".reference, [style*='display:none'], [style*='display: none'], .sortkey"
    ):
        junk.decompose()
    for br in node.find_all("br"):
        br.replace_with("; ")
    for li in node.find_all("li"):
        li.insert_after("; ")
    text = node.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*;\s*(;\s*)+", "; ", text)  # empty list items
    text = re.sub(r":\s*;\s*", ": ", text)          # "Songs: ; Vishal–Shekhar" -> "Songs: Vishal–Shekhar"
    text = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip(" ;")


# -----------------------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------------------
@lru_cache(maxsize=256)
def search_films(query: str, limit: int = 5) -> list[dict]:
    """Film articles that match `query`, best first: [{title, description, url}]."""
    query = " ".join((query or "").split())[:200]
    if not query:
        return []
    data = _api({
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} {FILM_FILTER}",
        "gsrlimit": max(1, min(limit, 10)),
        "prop": "description",
    })
    pages = sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0))
    return [
        {"title": p["title"], "description": p.get("description", ""), "url": page_url(p["title"])}
        for p in pages
        if "title" in p
    ]


# -----------------------------------------------------------------------------------------
# One film
# -----------------------------------------------------------------------------------------
def _parse(title: str, **params) -> dict | None:
    """action=parse for a page; None if the page doesn't exist."""
    data = _api({"action": "parse", "page": title, "redirects": 1, **params})
    if "error" in data:
        if data["error"].get("code") in ("missingtitle", "invalidtitle"):
            return None
        raise WikipediaError(f"Wikipedia couldn't open that page ({data['error'].get('code', 'error')})")
    return data.get("parse")


def _infobox_facts(soup: BeautifulSoup) -> dict[str, str]:
    box = soup.select_one("table.infobox")
    if box is None:
        return {}
    found: dict[str, str] = {}
    for row in box.select("tr"):
        label, value = row.find("th", class_="infobox-label"), row.find("td", class_="infobox-data")
        if label is None or value is None:
            continue
        name = label.get_text(" ", strip=True)
        text = _clean_html_text(value)
        if name in FACT_LABELS and text:
            found[name] = text[:MAX_FACT_CHARS] + (" …" if len(text) > MAX_FACT_CHARS else "")
    return {name: found[name] for name in FACT_LABELS if name in found}


def _summary(soup: BeautifulSoup) -> str:
    paragraphs = []
    for p in soup.find_all("p", recursive=True):
        if p.find_parent("table"):
            continue
        text = _clean_html_text(p)
        if len(text) > 40:
            paragraphs.append(text)
        if sum(len(t) for t in paragraphs) >= MAX_SUMMARY_CHARS:
            break
    return " ".join(paragraphs)[:MAX_SUMMARY_CHARS]


_SKIP_SECTIONS = {"references", "notes", "citations", "external links", "see also", "further reading",
                  "bibliography", "footnotes", "sources"}


@lru_cache(maxsize=256)
def _sections(title: str) -> tuple[dict, ...]:
    """The page's sections: ({name, index, anchor, level}, ...), without reference lists."""
    parsed = _parse(title, prop="sections") or {}
    found = []
    for s in parsed.get("sections", []):
        name = BeautifulSoup(s.get("line", ""), "html.parser").get_text().strip()
        if name and name.lower() not in _SKIP_SECTIONS:
            found.append({"name": name, "index": s.get("index"), "anchor": s.get("anchor") or name,
                          "level": int(s.get("toclevel") or 1)})
    return tuple(found)


def _load_film(title: str) -> dict | None:
    """The film page for an exact title, or None if it doesn't exist or isn't a film."""
    parsed = _parse(title, prop="text", section=0)
    if parsed is None:
        return None
    soup = BeautifulSoup(parsed.get("text", ""), "html.parser")
    facts = _infobox_facts(soup)
    if not facts:  # a person, a book, a disambiguation page ...
        return None
    return {
        "title": parsed["title"],
        "url": page_url(parsed["title"]),
        "facts": facts,
        "summary": _summary(soup),
        "sections": [s["name"] for s in _sections(parsed["title"]) if s["level"] <= 2],
    }


@lru_cache(maxsize=256)
def get_film(title: str, year: str = "") -> dict:
    """Facts for one film. Tries the exact title first, then a film search (so "Pathaan"
    finds "Pathaan (film)" and "Don 2006" finds the 2006 film).

    Returns {title, url, facts, summary, sections, other_matches} or raises WikipediaError.
    """
    title = " ".join((title or "").split())[:200]
    year = re.sub(r"\D", "", str(year or ""))[:4]
    if not title:
        raise WikipediaError("No film title was given")

    film = None if year else _load_film(title)
    matches = search_films(f"{title} {year}".strip(), 5)
    if film is None:
        for match in matches[:3]:
            if year and year not in match["description"] + match["title"]:
                continue
            film = _load_film(match["title"])
            if film:
                break
        if film is None and year:  # the year may be off by one; take the best match anyway
            film = next((f for f in (_load_film(m["title"]) for m in matches[:2]) if f), None)
    if film is None:
        raise WikipediaError(f"I couldn't find a film called “{title}”{f' ({year})' if year else ''} on Wikipedia")

    film["other_matches"] = [
        f"{m['title']} ({m['description']})" if m["description"] else m["title"]
        for m in matches
        if m["title"] != film["title"]
    ][:4]
    return film


# What people ask for -> what Wikipedia film pages call it (tried in order)
_SECTION_ALIASES = {
    "story": ["plot"], "synopsis": ["plot"], "storyline": ["plot"], "summary": ["plot"],
    "characters": ["cast"], "actors": ["cast"], "star cast": ["cast"],
    "collection": ["box office"], "collections": ["box office"], "earnings": ["box office"],
    "verdict": ["box office", "reception"], "budget": ["production", "box office"],
    "awards": ["accolades", "awards and nominations"], "songs": ["soundtrack", "music"],
    "soundtrack": ["music"], "music": ["soundtrack"], "reviews": ["critical response", "critical reception", "reception"],
    "review": ["critical response", "critical reception", "reception"], "release": ["release"],
}


@lru_cache(maxsize=256)
def get_section(title: str, section: str) -> dict:
    """The text of one section of a film's page, e.g. "Plot" or "Box office".

    Section names are matched loosely ("box-office", "story" -> "Plot"); if there's no such
    section, the error lists the sections that do exist.
    """
    film = get_film(title)
    wanted = " ".join((section or "").replace("-", " ").replace("_", " ").split()).lower()
    candidates = [wanted, *_SECTION_ALIASES.get(wanted, [])]

    names = {s["name"].lower(): s for s in _sections(film["title"])}
    choice = next((names[c] for c in candidates if c in names), None)
    if choice is None:  # "box office" also matches "Box office collection"
        choice = next((s for c in candidates for n, s in names.items() if c and c in n), None)
    if choice is None:
        close = get_close_matches(wanted, list(names), n=1, cutoff=0.6)
        choice = names[close[0]] if close else None
    if choice is None:
        available = ", ".join(film["sections"][:20]) or "none"
        raise WikipediaError(f"“{film['title']}” has no “{section}” section. Sections: {available}")

    parsed = _parse(film["title"], prop="text", section=choice["index"]) or {}
    soup = BeautifulSoup(parsed.get("text", ""), "html.parser")
    for junk in soup.select("table, figure, .thumb, .hatnote, .mw-heading, h2, h3, h4, h5, .reflist, .navbox, "
                            "div[role='note'], .toc, #toc, [role='navigation']"):
        junk.decompose()
    parts = []
    for node in soup.find_all(["p", "li"]):
        if node.name == "li" and node.find_parent("li"):
            continue
        text = _clean_html_text(node)
        if text:
            parts.append(("• " if node.name == "li" else "") + text)
    text = "\n".join(parts)
    return {
        "title": film["title"],
        "section": choice["name"],
        "url": page_url(film["title"], choice["anchor"]),
        "text": text[:MAX_SECTION_CHARS] + (" …" if len(text) > MAX_SECTION_CHARS else ""),
    }


def clear_cache() -> None:
    for fn in (search_films, get_film, get_section, _sections):
        fn.cache_clear()
