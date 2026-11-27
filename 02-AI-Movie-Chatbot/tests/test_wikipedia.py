import json

import pytest
import requests

from movie import wikipedia
from movie.tools import run_tool, status_line
from movie.wikipedia import WikipediaError, get_film, get_section, page_url, search_films


def test_search_returns_films_best_first(fake_wiki):
    results = search_films("Rocket Raja")
    assert [r["title"] for r in results] == ["Rocket Raja (film)", "Rocket Raja (1990 film)"]
    assert results[0]["url"] == "https://en.wikipedia.org/wiki/Rocket_Raja_(film)"
    assert 'hastemplate:"Infobox film"' in fake_wiki.calls[0]["gsrsearch"]  # only film articles


def test_empty_search_makes_no_request(fake_wiki):
    assert search_films("   ") == [] and fake_wiki.calls == []


def test_a_non_film_page_falls_back_to_the_film(fake_wiki):
    film = get_film("Rocket Raja")  # the exact title is a disambiguation page
    assert film["title"] == "Rocket Raja (film)"
    assert film["other_matches"] == ["Rocket Raja (1990 film) (1990 Indian film)"]


def test_infobox_facts_are_clean(fake_wiki):
    facts = get_film("Rocket Raja (film)")["facts"]
    assert facts["Directed by"] == "Asha Rao"  # no [1]
    assert facts["Starring"] == "Vikram Dev; Meera Nair"
    assert facts["Music by"] == "Songs: Duo Beats; Score: K. Ravi"
    assert facts["Release date"] == "26 January 2024"  # hidden ISO date dropped
    assert facts["Budget"] == "₹100 crore" and facts["Box office"] == "est. ₹350 crore"
    assert "Cinematographer's dog" not in facts  # only useful rows
    assert list(facts)[0] == "Directed by"


def test_summary_and_sections(fake_wiki):
    film = get_film("Rocket Raja (film)")
    assert film["summary"].startswith("Rocket Raja is a 2024") and "commercial success" in film["summary"]
    assert "[5]" not in film["summary"] and "Short." not in film["summary"]
    assert film["sections"] == ["Plot", "Cast", "Release", "Box office", "Rocket Raja 2"]  # no References


def test_year_picks_the_right_film(fake_wiki):
    assert get_film("Rocket Raja", "1990")["title"] == "Rocket Raja (1990 film)"


def test_unknown_film(fake_wiki):
    with pytest.raises(WikipediaError, match="couldn't find a film called “Nope”"):
        get_film("Nope")
    with pytest.raises(WikipediaError):
        get_film("   ")


@pytest.mark.parametrize("asked, found", [
    ("Plot", "Plot"), ("story", "Plot"), ("characters", "Cast"), ("collection", "Box office"),
    ("box-office", "Box office"), ("verdict", "Box office"), ("Box offce", "Box office"),
])
def test_sections_are_matched_loosely(fake_wiki, asked, found):
    assert get_section("Rocket Raja (film)", asked)["section"] == found


def test_section_text_is_clean(fake_wiki):
    plot = get_section("Rocket Raja (film)", "Plot")
    assert plot["text"] == "A mechanic builds a rocket in his village."  # no heading or contents box
    assert plot["url"].endswith("Rocket_Raja_(film)#Plot")
    assert get_section("Rocket Raja (film)", "Cast")["text"] == "• Vikram Dev as Raja\n• Meera Nair as Tara"
    box = get_section("Rocket Raja (film)", "Box office")["text"]
    assert box == "It earned ₹40 crore on day one.\nIt was declared a blockbuster."  # no [9], no table


def test_missing_section_lists_the_real_ones(fake_wiki):
    with pytest.raises(WikipediaError, match="Sections: Plot, Cast, Release, Box office"):
        get_section("Rocket Raja (film)", "Soundtrack")


def test_lookups_are_cached(fake_wiki):
    get_film("Rocket Raja (film)")
    count = len(fake_wiki.calls)
    get_film("Rocket Raja (film)")
    assert len(fake_wiki.calls) == count


@pytest.mark.parametrize("error, message", [
    (requests.ConnectionError("down"), "couldn't be reached"),
    (requests.Timeout("slow"), "too long"),
])
def test_network_problems_become_friendly_errors(monkeypatch, error, message):
    def broken(*args, **kwargs):
        raise error

    monkeypatch.setattr(wikipedia.requests, "get", broken)
    with pytest.raises(WikipediaError, match=message):
        wikipedia._api({"action": "query"})


def test_page_url():
    assert page_url("Baahubali 2: The Conclusion") == "https://en.wikipedia.org/wiki/Baahubali_2:_The_Conclusion"
    assert page_url("Pathaan (film)", "Box office") == "https://en.wikipedia.org/wiki/Pathaan_(film)#Box_office"


# ---- tools ------------------------------------------------------------------------------------
def test_get_movie_tool_returns_facts_and_a_source(fake_wiki):
    result = run_tool("get_movie", {"title": "Rocket Raja"})
    data = json.loads(result.content)
    assert data["title"] == "Rocket Raja (film)" and data["facts"]["Budget"] == "₹100 crore"
    assert data["cast_and_characters"] == ["Vikram Dev as Raja", "Meera Nair as Tara"]
    assert [s.url for s in result.sources] == ["https://en.wikipedia.org/wiki/Rocket_Raja_(film)"]


def test_section_tool_source_points_to_the_section(fake_wiki):
    result = run_tool("get_movie_section", {"title": "Rocket Raja (film)", "section": "Box office"})
    assert result.sources[0].title == "Rocket Raja (film) › Box office"
    assert result.sources[0].url.endswith("#Box_office")


def test_tool_errors_are_returned_not_raised(fake_wiki):
    assert "couldn't find" in json.loads(run_tool("get_movie", {"title": "Nope"}).content)["error"]
    assert "Unknown tool" in json.loads(run_tool("delete_everything", {}).content)["error"]
    assert json.loads(run_tool("search_movies", {"query": "zzz"}).content)["note"]


def test_unexpected_failures_dont_crash(monkeypatch):
    def boom(*args):
        raise KeyError("odd page")

    monkeypatch.setattr(wikipedia, "get_film", boom)
    assert "lookup failed" in json.loads(run_tool("get_movie", {"title": "x"}).content)["error"]


def test_long_results_are_cut(fake_wiki):
    assert len(run_tool("get_movie", {"title": "Rocket Raja"}, max_chars=100).content) < 130


def test_status_lines():
    assert status_line("get_movie", {"title": "Sholay"}) == "🔎 Looking up *Sholay* on Wikipedia…"
    assert status_line("get_movie_section", {"title": "Sholay"}) == "🔧 Working…"  # missing section name
    assert status_line("unknown", {}) == "🔧 Working…"


def test_film_without_a_cast_section_still_works(fake_wiki, monkeypatch):
    from tests import conftest

    monkeypatch.setattr(conftest, "SECTIONS", [s for s in conftest.SECTIONS if s["line"] != "Cast"])
    data = json.loads(run_tool("get_movie", {"title": "Rocket Raja"}).content)
    assert "cast_and_characters" not in data and data["facts"]
