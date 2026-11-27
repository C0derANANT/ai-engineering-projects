"""Shared fakes. Tests never use the internet or an API key: Wikipedia and the LLM are faked."""

from types import SimpleNamespace

import pytest

from movie import wikipedia

# ---- a made-up film on a fake Wikipedia ------------------------------------------------------
INFOBOX = """
<table class="infobox vevent"><tbody>
<tr><th colspan="2" class="infobox-above summary">Rocket Raja</th></tr>
<tr><th class="infobox-label">Directed by</th><td class="infobox-data">Asha Rao<sup class="reference">[1]</sup></td></tr>
<tr><th class="infobox-label">Starring</th><td class="infobox-data"><div class="plainlist"><ul>
  <li>Vikram Dev</li><li>Meera Nair</li></ul></div></td></tr>
<tr><th class="infobox-label">Music by</th><td class="infobox-data">Songs:<br>Duo Beats<br>Score:<br>K. Ravi</td></tr>
<tr><th class="infobox-label">Release date</th><td class="infobox-data">26 January 2024<span style="display:none"> (<span class="bday">2024-01-26</span>)</span></td></tr>
<tr><th class="infobox-label">Budget</th><td class="infobox-data">₹100 crore<sup class="reference">[2]</sup><sup class="reference">[3]</sup></td></tr>
<tr><th class="infobox-label">Box office</th><td class="infobox-data">est. ₹350 crore<sup class="reference">[4]</sup></td></tr>
<tr><th class="infobox-label">Cinematographer's dog</th><td class="infobox-data">Bruno</td></tr>
</tbody></table>
"""
LEAD = INFOBOX + """
<p>Short.</p>
<p><b>Rocket Raja</b> is a 2024 Indian Hindi-language space comedy film directed by Asha Rao.<sup class="reference">[5]</sup></p>
<p>Made on a budget of ₹100 crore, it grossed ₹350 crore worldwide and was a commercial success.</p>
"""
SECTIONS = [
    {"index": "1", "line": "Plot", "anchor": "Plot", "toclevel": 1},
    {"index": "2", "line": "Cast", "anchor": "Cast", "toclevel": 1},
    {"index": "3", "line": "Release", "anchor": "Release", "toclevel": 1},
    {"index": "4", "line": "Box office", "anchor": "Box_office", "toclevel": 2},
    {"index": "5", "line": "<i>Rocket Raja 2</i>", "anchor": "Rocket_Raja_2", "toclevel": 1},
    {"index": "6", "line": "References", "anchor": "References", "toclevel": 1},
]
SECTION_HTML = {
    "1": '<div class="mw-heading"><h2>Plot</h2></div><p>A mechanic builds a rocket in his village.</p>'
         '<div id="toc" class="toc"><ul><li>1 Plot</li></ul></div>',
    "2": "<ul><li>Vikram Dev as Raja</li><li>Meera Nair as Tara</li></ul>",
    "4": '<p>It earned ₹40 crore on day one.<sup class="reference">[9]</sup></p>'
         "<table><tr><td>chart</td></tr></table><p>It was declared a blockbuster.</p>",
}
SEARCH = {
    "rocket raja": [
        {"title": "Rocket Raja (film)", "index": 1, "description": "2024 Indian film by Asha Rao"},
        {"title": "Rocket Raja (1990 film)", "index": 2, "description": "1990 Indian film"},
    ],
    "rocket raja 1990": [
        {"title": "Rocket Raja (1990 film)", "index": 1, "description": "1990 Indian film"},
        {"title": "Rocket Raja (film)", "index": 2, "description": "2024 Indian film by Asha Rao"},
    ],
}
PAGES = {
    "Rocket Raja": "<p>Rocket Raja may refer to: a film, a song.</p>",  # disambiguation: no infobox
    "Rocket Raja (film)": LEAD,
    "Rocket Raja (1990 film)": INFOBOX.replace("2024", "1990").replace("Asha Rao", "Old Director"),
}


class FakeWikipedia:
    def __init__(self):
        self.calls = []

    def __call__(self, params):
        self.calls.append(params)
        if params.get("action") == "query":
            query = params["gsrsearch"].replace(wikipedia.FILM_FILTER, "").strip().lower()
            return {"query": {"pages": list(reversed(SEARCH.get(query, [])))}}  # unsorted on purpose
        title = params["page"]
        if title not in PAGES:
            return {"error": {"code": "missingtitle", "info": "The page you specified doesn't exist."}}
        if params.get("prop") == "sections":
            return {"parse": {"title": title, "sections": SECTIONS}}
        section = str(params.get("section", ""))
        html = PAGES[title] if section == "0" else SECTION_HTML.get(section, "<p>Nothing here.</p>")
        return {"parse": {"title": title, "text": html}}


@pytest.fixture
def fake_wiki(monkeypatch):
    fake = FakeWikipedia()
    monkeypatch.setattr(wikipedia, "_api", fake)
    wikipedia.clear_cache()
    yield fake
    wikipedia.clear_cache()


# ---- a scripted OpenAI-compatible client ------------------------------------------------------
def _text_chunks(text):
    words = text.split(" ")
    for i, word in enumerate(words):
        piece = word + (" " if i < len(words) - 1 else "")
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece, tool_calls=None))])


def _tool_chunks(calls):
    for index, call in enumerate(calls):
        args = call.get("arguments", "{}")
        half = len(args) // 2
        extra = {"extra_content": call["extra"]} if "extra" in call else {}
        first = SimpleNamespace(index=index, id=call.get("id"), model_extra=extra,
                                function=SimpleNamespace(name=call["name"], arguments=args[:half]))
        second = SimpleNamespace(index=index, id=None, model_extra={},
                                 function=SimpleNamespace(name=None, arguments=args[half:]))
        for tc in (first, second):  # arguments arrive in two pieces, as when streaming
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[tc]))])


class FakeLLMClient:
    """Each create() call plays the next scripted reply: a string (streamed), a list of tool
    calls ({"name", "arguments", "id"?, "extra"?}), or an exception to raise."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, model, messages, stream, **kwargs):
        self.calls.append({"model": model, "messages": [dict(m) for m in messages], **kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return iter(list(_text_chunks(reply) if isinstance(reply, str) else _tool_chunks(reply)))
