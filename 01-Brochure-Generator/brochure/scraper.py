"""Scrapes a company website (homepage + a few key pages) for brochure context."""

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
}
TIMEOUT = 10
MAX_CHARS_PER_PAGE = 5_000
MAX_TOTAL_CHARS = 15_000
MAX_EXTRA_PAGES = 3

# Pages most useful for a brochure, in priority order
KEY_PAGE_PATTERN = re.compile(
    r"about|company|who-we-are|services|solutions|products|what-we-do|careers|team|mission",
    re.IGNORECASE,
)


@dataclass
class WebsiteContext:
    url: str
    title: str = ""
    description: str = ""
    pages: dict[str, str] = field(default_factory=dict)  # url -> text

    def as_prompt(self) -> str:
        parts = [f"Website: {self.url}"]
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.description:
            parts.append(f"Meta description: {self.description}")
        for page_url, text in self.pages.items():
            parts.append(f"\n--- Page: {page_url} ---\n{text}")
        return "\n".join(parts)[:MAX_TOTAL_CHARS]


def normalize_url(url: str) -> str | None:
    """Add https:// if missing; return None if it isn't a valid http(s) URL."""
    url = (url or "").strip()
    if not url:
        return None
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or "." not in parsed.netloc:
        return None
    return url


def _fetch_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser")


def _visible_text(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    for tag in body(["script", "style", "noscript", "svg", "img", "input", "nav", "footer", "form"]):
        tag.decompose()
    text = body.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return text[:MAX_CHARS_PER_PAGE]


def _key_page_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Same-site links that look like About / Services / Careers pages."""
    base_host = urlparse(base_url).netloc.removeprefix("www.")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        link = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.removeprefix("www.") != base_host:
            continue
        if link.rstrip("/") == base_url.rstrip("/") or link in found:
            continue
        if KEY_PAGE_PATTERN.search(parsed.path):
            found.append(link)
    return found[:MAX_EXTRA_PAGES]


def fetch_website_context(url: str) -> WebsiteContext:
    """Scrape the homepage plus up to 3 key pages. Raises requests errors for the homepage."""
    soup = _fetch_soup(url)
    ctx = WebsiteContext(url=url)
    if soup.title and soup.title.string:
        ctx.title = soup.title.string.strip()
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        ctx.description = meta["content"].strip()

    extra_links = _key_page_links(soup, url)
    ctx.pages[url] = _visible_text(soup)

    for link in extra_links:
        try:
            ctx.pages[link] = _visible_text(_fetch_soup(link))
        except requests.RequestException as e:  # A failed sub-page is not fatal
            logger.warning("Skipping %s: %s", link, e)

    logger.info("Scraped %d page(s) from %s", len(ctx.pages), url)
    return ctx
