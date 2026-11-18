"""Scrapes a company website (homepage + a few key pages) for brochure context."""

import ipaddress
import logging
import os
import re
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = (5, 10)          # seconds to connect, seconds to wait between bytes
SCRAPE_BUDGET = 25         # seconds for the whole site; later sub-pages are skipped
MAX_BYTES = 2_000_000      # only read the first ~2 MB of a page
MAX_REDIRECTS = 5
MAX_CHARS_PER_PAGE = 5_000
MAX_TOTAL_CHARS = 15_000
MAX_EXTRA_PAGES = 3
THIN_CONTENT_CHARS = 300   # less text than this usually means a JavaScript-only site

# Pages most useful for a brochure. One page is taken from each group, best keyword first.
KEY_PAGE_GROUPS = [
    ["about", "who-we-are", "our-story", "company"],
    ["services", "solutions", "products", "what-we-do", "platform"],
    ["contact", "careers", "jobs", "mission", "culture", "team"],
]
_SKIP_EXTENSIONS = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|mp4|mp3|docx?|xlsx?)$", re.IGNORECASE)


class ScrapeError(Exception):
    """The website couldn't be read. The message is written for end users."""


@dataclass
class WebsiteContext:
    url: str
    title: str = ""
    description: str = ""
    pages: dict[str, str] = field(default_factory=dict)  # url -> text
    contact: list[str] = field(default_factory=list)     # emails, phones, footer text

    @property
    def text_chars(self) -> int:
        return sum(len(text) for text in self.pages.values())

    @property
    def is_thin(self) -> bool:
        """True when the site gave almost no readable text (JavaScript-only or blocked)."""
        return self.text_chars < THIN_CONTENT_CHARS

    def as_prompt(self) -> str:
        parts = [f"Website: {self.url}"]
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.description:
            parts.append(f"Meta description: {self.description}")
        if self.contact:
            parts.append("Contact details found on the site:\n" + "\n".join(self.contact))
        for page_url, text in self.pages.items():
            parts.append(f"\n--- Page: {page_url} ---\n{text}")
        return "\n".join(parts)[:MAX_TOTAL_CHARS]


def normalize_url(url: str) -> str | None:
    """Add https:// if missing; return None if it isn't a valid http(s) URL."""
    url = (url or "").strip()
    if not url:
        return None
    if not re.match(r"^https?://", url, re.IGNORECASE):
        if "://" in url:  # ftp://, file:// and friends
            return None
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        parsed.port  # raises ValueError for ports like ":abc"
    except ValueError:
        return None
    if "." not in host or " " in host:
        return None
    return url


def _check_public_host(url: str) -> None:
    """Refuse URLs that resolve to private, local or reserved addresses.

    The app can be shared publicly (share=True), so without this anyone with the
    link could make your computer fetch pages from your home network or router.
    Set ALLOW_PRIVATE_URLS=1 to switch this off for local testing.
    """
    if os.getenv("ALLOW_PRIVATE_URLS") == "1":
        return
    host = urlparse(url).hostname or ""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError) as e:
        raise ScrapeError("that website address doesn't exist (check the spelling)") from e
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise ScrapeError("it points to a private or local network address, which isn't allowed")


def _fetch(session: requests.Session, url: str, deadline: float) -> tuple[str, BeautifulSoup]:
    """Download one HTML page, following redirects safely. Returns (final_url, soup)."""
    for _ in range(MAX_REDIRECTS + 1):
        _check_public_host(url)
        response = session.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False)
        if not response.is_redirect:
            break
        response.close()
        url = urljoin(url, response.headers["Location"])
        if urlparse(url).scheme not in ("http", "https"):
            raise ScrapeError("it redirects to something that isn't a web page")
    else:
        raise ScrapeError("it redirects too many times")

    with response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not any(t in content_type for t in ("html", "xml", "text/plain")):
            raise ScrapeError(f"it isn't a web page (the server sent {content_type.split(';')[0]})")
        body = bytearray()
        for chunk in response.iter_content(64 * 1024):
            body += chunk
            if len(body) >= MAX_BYTES or time.monotonic() > deadline:
                logger.info("Only reading the first %d KB of %s", len(body) // 1024, url)
                break
        encoding = response.encoding if "charset=" in content_type else None
    return url, BeautifulSoup(bytes(body), "html.parser", from_encoding=encoding)


def _describe(error: Exception) -> str:
    """Turn a scraping exception into a short reason a user can act on."""
    if isinstance(error, ScrapeError):
        return str(error)
    if isinstance(error, requests.Timeout):
        return "it took too long to respond"
    if isinstance(error, requests.HTTPError) and error.response is not None:
        code = error.response.status_code
        if code in (401, 403, 429, 503):
            return f"it blocks automated visitors (HTTP {code})"
        if code == 404:
            return "that page doesn't exist (HTTP 404)"
        return f"the server returned an error (HTTP {code})"
    if isinstance(error, requests.exceptions.SSLError):
        return "its security certificate couldn't be verified"
    if isinstance(error, requests.ConnectionError):
        return "couldn't connect to it (check the address)"
    return "it couldn't be read"


def _contact_details(soup: BeautifulSoup) -> list[str]:
    """Emails and phone numbers from mailto:/tel: links, plus the footer text."""
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        scheme = href.split(":", 1)[0].lower()
        if scheme in ("mailto", "tel"):
            value = unquote(href.split(":", 1)[1].split("?")[0]).strip()
            item = f"{'Email' if scheme == 'mailto' else 'Phone'}: {value}"
            if value and item not in found:
                found.append(item)
    footer = soup.find("footer")
    if footer:
        text = re.sub(r"\s+", " ", footer.get_text(" ", strip=True))
        if text:
            found.append(f"Footer: {text[:600]}")
    return found


def _visible_text(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    for tag in body(["script", "style", "noscript", "svg", "img", "input", "nav", "footer", "form"]):
        tag.decompose()
    text = body.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return text[:MAX_CHARS_PER_PAGE]


def _key_page_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Same-site links to About / Services / Contact-style pages, best first."""
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")
    scores: dict[str, tuple[int, int, int, int]] = {}
    for a in soup.find_all("a", href=True):
        link = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        parsed = urlparse(link)
        path = parsed.path.lower()
        if parsed.scheme not in ("http", "https") or parsed.netloc.lower().removeprefix("www.") != base_host:
            continue
        if link == base_url.rstrip("/") or link in scores or _SKIP_EXTENSIONS.search(path):
            continue
        for group, keywords in enumerate(KEY_PAGE_GROUPS):
            rank = next((i for i, word in enumerate(keywords) if word in path), None)
            if rank is not None:
                scores[link] = (group, rank, path.count("/"), len(link))
                break

    ranked = sorted(scores, key=scores.get)
    picked = [next(link for link in ranked if scores[link][0] == group)
              for group in range(len(KEY_PAGE_GROUPS))
              if any(scores[link][0] == group for link in ranked)]
    picked += [link for link in ranked if link not in picked]
    return picked[:MAX_EXTRA_PAGES]


def fetch_website_context(url: str) -> WebsiteContext:
    """Scrape the homepage plus up to 3 key pages.

    Raises ScrapeError if the homepage can't be read; failed sub-pages are skipped.
    """
    deadline = time.monotonic() + SCRAPE_BUDGET
    with requests.Session() as session:
        session.headers.update(HEADERS)
        try:
            final_url, soup = _fetch(session, url, deadline)
        except Exception as e:
            logger.warning("Could not read %s: %s", url, e)
            raise ScrapeError(_describe(e)) from e

        ctx = WebsiteContext(url=final_url)
        if soup.title:
            ctx.title = soup.title.get_text(" ", strip=True)
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        if meta and meta.get("content"):
            ctx.description = meta["content"].strip()
        ctx.contact = _contact_details(soup)
        extra_links = _key_page_links(soup, final_url)
        ctx.pages[final_url] = _visible_text(soup)

        for link in extra_links:
            if time.monotonic() > deadline:
                logger.warning("Scrape time budget used up; skipping the remaining pages")
                break
            try:
                page_url, page = _fetch(session, link, deadline)
            except Exception as e:  # A failed sub-page is not fatal
                logger.warning("Skipping %s: %s", link, e)
                continue
            for item in _contact_details(page):
                is_extra_footer = item.startswith("Footer:") and any(c.startswith("Footer:") for c in ctx.contact)
                if item not in ctx.contact and not is_extra_footer:
                    ctx.contact.append(item)
            text = _visible_text(page)
            if text:
                ctx.pages[page_url] = text

    ctx.contact = ctx.contact[:12]
    logger.info("Scraped %d page(s), %d characters from %s", len(ctx.pages), ctx.text_chars, final_url)
    return ctx
