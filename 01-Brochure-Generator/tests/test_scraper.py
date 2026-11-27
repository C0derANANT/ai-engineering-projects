"""Tests for brochure/scraper.py. None of them use the internet: DNS lookups are faked."""

import io
import socket

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from brochure import scraper
from brochure.scraper import (
    MAX_CHARS_PER_PAGE,
    ScrapeError,
    _cf_decode,
    _check_public_host,
    _contact_details,
    _reveal_cf_emails,
    _key_page_links,
    _logo_candidates,
    _usable_logo,
    _visible_text,
    normalize_url,
)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# --------------------------------------------------------------------------
# normalize_url
# --------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("huggingface.co", "https://huggingface.co"),
    ("  https://groq.com/about  ", "https://groq.com/about"),
    ("http://example.com:8080/page", "http://example.com:8080/page"),
    ("HTTPS://Example.com", "HTTPS://Example.com"),
    ("www.chaipoint.com/menu?city=delhi", "https://www.chaipoint.com/menu?city=delhi"),
])
def test_normalize_url_accepts_websites(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", None,
    "ftp://example.com",        # not a web page
    "file:///etc/passwd",       # a file on the server
    "localhost",                # no dot in the host name
    "not a website",
    "https://exa mple.com",     # space in the host name
    "https://example.com:abc",  # port isn't a number
])
def test_normalize_url_rejects_bad_input(raw):
    assert normalize_url(raw) is None


# --------------------------------------------------------------------------
# _check_public_host (SSRF protection)
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def no_private_url_override(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_URLS", raising=False)


def fake_dns(monkeypatch, *addresses):
    """Make every host name resolve to `addresses`."""
    def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in addresses]
    monkeypatch.setattr(scraper.socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize("address", [
    "127.0.0.1",        # this machine
    "10.0.0.5",         # home / office networks
    "172.16.0.1",
    "192.168.1.1",      # a typical router
    "169.254.169.254",  # cloud servers' secret metadata address
    "100.64.0.1",       # carrier-grade NAT
    "0.0.0.0",
    "::1",              # this machine, IPv6
    "fd00::1",          # private IPv6
    "fe80::1%eth0",     # link-local IPv6 with an interface name
])
def test_private_addresses_are_refused(monkeypatch, address):
    fake_dns(monkeypatch, address)
    with pytest.raises(ScrapeError, match="private or local"):
        _check_public_host("https://sneaky.example.com/")


def test_public_addresses_are_allowed(monkeypatch):
    fake_dns(monkeypatch, "93.184.215.14", "2606:4700::6810:84e5")
    _check_public_host("https://example.com/")  # no error


def test_one_private_address_among_public_ones_is_refused(monkeypatch):
    fake_dns(monkeypatch, "93.184.215.14", "127.0.0.1")
    with pytest.raises(ScrapeError):
        _check_public_host("https://example.com/")


def test_unknown_host_gives_a_friendly_error(monkeypatch):
    def getaddrinfo(*args, **kwargs):
        raise socket.gaierror("Name or service not known")
    monkeypatch.setattr(scraper.socket, "getaddrinfo", getaddrinfo)
    with pytest.raises(ScrapeError, match="doesn't exist"):
        _check_public_host("https://no-such-company-xyz.com/")


def test_private_check_can_be_switched_off_for_local_testing(monkeypatch):
    fake_dns(monkeypatch, "127.0.0.1")
    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "1")
    _check_public_host("http://localhost.example:7860/")  # no error


# --------------------------------------------------------------------------
# _visible_text
# --------------------------------------------------------------------------
def test_visible_text_keeps_content_and_drops_page_furniture():
    page = soup("""
        <html><head><title>Acme</title><style>.x { color: red }</style></head>
        <body>
          <nav>Home | About | Login</nav>
          <script>var tracking = "secret";</script>
          <h1>Acme Rockets</h1>
          <p>We build rockets.</p>


          <p>Safe and fast.</p>
          <noscript>Please enable JavaScript</noscript>
          <form><input value="email">Sign up</form>
          <svg><text>icon</text></svg>
          <footer>© Acme 2026</footer>
        </body></html>
    """)
    assert _visible_text(page) == "Acme Rockets\nWe build rockets.\nSafe and fast."


def test_visible_text_is_capped_per_page():
    page = soup("<body><p>" + "a" * (MAX_CHARS_PER_PAGE + 1000) + "</p></body>")
    assert len(_visible_text(page)) == MAX_CHARS_PER_PAGE


def test_visible_text_works_without_a_body_tag():
    assert _visible_text(soup("Just some text")) == "Just some text"


# --------------------------------------------------------------------------
# _key_page_links
# --------------------------------------------------------------------------
def links_page(*hrefs: str) -> BeautifulSoup:
    return soup("".join(f'<a href="{href}">link</a>' for href in hrefs))


def test_key_page_links_picks_the_best_page_from_each_group():
    page = links_page(
        "/company/history",            # about group, weaker keyword
        "/about-us",                   # about group, best keyword
        "/products",
        "/services",                   # services group, best keyword
        "/careers",
        "https://www.acme.test/contact",  # www. counts as the same site
        "/blog",                       # not a key page
    )
    assert _key_page_links(page, "https://acme.test/") == [
        "https://acme.test/about-us",
        "https://acme.test/services",
        "https://www.acme.test/contact",
    ]


def test_key_page_links_skips_other_sites_files_and_the_homepage():
    page = links_page(
        "https://other-company.com/about",  # another website
        "/brochure.pdf", "/team-photo.JPG",  # files, not pages
        "/",                                 # the homepage itself
        "mailto:hello@acme.test",
        "/about#team", "/about",             # same page twice (fragment removed)
    )
    assert _key_page_links(page, "https://acme.test/") == ["https://acme.test/about"]


def test_key_page_links_returns_at_most_three():
    page = links_page("/about", "/our-story", "/services", "/platform", "/contact", "/jobs")
    assert len(_key_page_links(page, "https://acme.test")) == 3


def test_key_page_links_with_no_matches_is_empty():
    assert _key_page_links(links_page("/blog", "/pricing"), "https://acme.test") == []


# --------------------------------------------------------------------------
# Logo
# --------------------------------------------------------------------------
def test_logo_candidates_are_ordered_best_first():
    page = soup("""<head>
        <link rel="icon" href="/favicon-32.png" sizes="32x32">
        <link rel="icon" type="image/svg+xml" href="/icon.svg">
        <link rel="icon" href="/icon-192.png" sizes="192x192">
        <link rel="apple-touch-icon" href="/apple-touch-icon.png">
        <link rel="icon" href="data:image/png;base64,iVBORw0KGgo=">
        <meta property="og:image" content="//cdn.acme.test/og.png">
        <link rel="shortcut icon" href="/favicon.ico">
    </head>""")
    assert _logo_candidates(page, "https://acme.test/about") == [
        "https://acme.test/apple-touch-icon.png",
        "https://acme.test/icon-192.png",
        "https://cdn.acme.test/og.png",
        "https://acme.test/favicon.ico",
    ]


def test_logo_candidates_guess_the_usual_paths():
    assert _logo_candidates(soup("<head></head>"), "https://acme.test/") == [
        "https://acme.test/apple-touch-icon.png",
        "https://acme.test/favicon.ico",
    ]


def image_bytes(width: int, height: int, fmt: str = "PNG", mode: str = "RGBA") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height)).save(buffer, fmt)
    return buffer.getvalue()


def test_usable_logo_returns_a_png():
    logo = _usable_logo(image_bytes(180, 180, "JPEG", "RGB"))
    assert logo is not None and logo.startswith(b"\x89PNG")


def test_usable_logo_shrinks_big_images():
    logo = _usable_logo(image_bytes(2000, 1600))
    assert Image.open(io.BytesIO(logo)).size == (512, 410)


@pytest.mark.parametrize("data", [
    image_bytes(32, 32),                    # tiny favicon: blurry in print
    image_bytes(1200, 630),                 # social-share photo, not a logo
    image_bytes(5000, 5000, mode="1"),      # 25 million pixels: too big to unpack
    b"<html>Not found</html>",              # an error page, not an image
    b"",
])
def test_usable_logo_rejects_unsuitable_files(data):
    assert _usable_logo(data) is None


# --------------------------------------------------------------------------
# Cloudflare email protection
# --------------------------------------------------------------------------
def _cf_encode(email: str, key: int = 0x42) -> str:
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


def test_cloudflare_hidden_emails_are_revealed():
    code = _cf_encode("support@acme.com")
    page = soup(
        f'<body><p>Write to <span class="__cf_email__" data-cfemail="{code}">[email&#160;protected]</span></p>'
        f'<a href="/cdn-cgi/l/email-protection#{_cf_encode("sales@acme.com")}">[email&#160;protected]</a></body>'
    )
    _reveal_cf_emails(page)
    assert "support@acme.com" in _visible_text(soup(str(page)))
    assert "Email: sales@acme.com" in _contact_details(page)
    assert "protected" not in str(page)


@pytest.mark.parametrize("code", ["", "zz", "42", "4202"])
def test_broken_cloudflare_codes_are_left_alone(code):
    assert _cf_decode(code) is None
