"""Tests for the prompt in brochure/generator.py (no AI call is made)."""

from brochure.generator import BrochureRequest, _build_messages
from brochure.scraper import WebsiteContext


def test_prompt_asks_for_the_website_first_in_get_in_touch():
    request = BrochureRequest("Acme", website=WebsiteContext(url="https://acme.test"))
    system, user = (message["content"] for message in _build_messages(request))
    assert '"- **Website:** [example.com](https://example.com)"' in system
    assert "Never invent phone numbers" in system
    assert "Website: https://acme.test" in user  # the address the AI is told to use


def test_prompt_without_a_website_says_so():
    system, user = (message["content"] for message in _build_messages(BrochureRequest("Acme")))
    assert "No website was provided." in user
