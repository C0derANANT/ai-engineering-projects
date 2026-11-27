"""The Wikipedia lookups, described for the LLM's tool calling (OpenAI function format)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import wikipedia
from .wikipedia import WikipediaError

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_movie",
            "description": (
                "One film's Wikipedia facts (director, writers, cast, music, studio, release date, runtime, "
                "budget, box office), its summary, and other films with similar titles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Film title, e.g. 'Pathaan'"},
                    "year": {"type": "string", "description": "Release year, if known"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_movie_section",
            "description": (
                "One section of a film's Wikipedia page: Plot, Cast, Box office, Critical response, "
                "Production, Music, Accolades ..."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Film title as returned by get_movie"},
                    "section": {"type": "string", "description": "Section name, e.g. 'Plot'"},
                },
                "required": ["title", "section"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_movies",
            "description": (
                "Search Wikipedia for films by words, e.g. 'Rajamouli films' or 'Nolan dream heist'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Words to search for"}},
                "required": ["query"],
            },
        },
    },
]

# Shown in the chat while a tool runs
STATUS = {
    "get_movie": "🔎 Looking up *{title}* on Wikipedia…",
    "get_movie_section": "📖 Reading the {section} section of *{title}*…",
    "search_movies": "🔎 Searching Wikipedia for “{query}”…",
}


@dataclass
class Source:
    title: str
    url: str


@dataclass
class ToolResult:
    content: str  # JSON for the model
    sources: list[Source] = field(default_factory=list)


def status_line(name: str, args: dict) -> str:
    template = STATUS.get(name, "🔧 Working…")
    try:
        return template.format(**{k: str(v)[:60] for k, v in args.items()})
    except (KeyError, IndexError):
        return "🔧 Working…"


def _cast_lines(title: str, limit: int = 10, max_chars: int = 800) -> list[str]:
    """The first lines of the film's Cast section ("Prabhas as Amarendra Baahubali"), or []."""
    try:
        text = wikipedia.get_section(title, "Cast")["text"]
    except Exception:  # no Cast section, or Wikipedia hiccup: the facts are still useful
        return []
    lines, total = [], 0
    for line in text.splitlines():
        line = line.lstrip("• ").strip()
        if not line or total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
        if len(lines) == limit:
            break
    return lines


def run_tool(name: str, args: dict, max_chars: int = 6000) -> ToolResult:
    """Run one tool call. Errors come back as {"error": ...} for the model, never as exceptions."""
    sources: list[Source] = []
    try:
        if name == "get_movie":
            film = wikipedia.get_film(str(args.get("title", "")), str(args.get("year", "") or ""))
            result = {"title": film["title"], "facts": film["facts"], "summary": film["summary"]}
            if cast := _cast_lines(film["title"]):
                result["cast_and_characters"] = cast  # models skip a second lookup for "who played whom"
            result["other_matches"] = film["other_matches"][:3]
            sources.append(Source(film["title"], film["url"]))
        elif name == "get_movie_section":
            section = wikipedia.get_section(str(args.get("title", "")), str(args.get("section", "")))
            result = section
            sources.append(Source(f"{section['title']} › {section['section']}", section["url"]))
        elif name == "search_movies":
            result = {"results": wikipedia.search_films(str(args.get("query", "")), 5)}
            if not result["results"]:
                result["note"] = "No film articles matched. Try other words or the original title."
        else:
            result = {"error": f"Unknown tool '{name}'. Use get_movie, get_movie_section or search_movies."}
    except WikipediaError as exc:
        result = {"error": str(exc)}
    except Exception as exc:  # a bug or an odd page must not crash the chat
        result = {"error": f"The lookup failed ({type(exc).__name__})."}
    content = json.dumps(result, ensure_ascii=False)
    if len(content) > max_chars:
        content = content[:max_chars] + '…" (cut short)'
    return ToolResult(content, sources)
