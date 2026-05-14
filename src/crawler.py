import logging
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE_URL = "https://quotes.toscrape.com"
POLITENESS_WINDOW = 6  # seconds

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(
        self, base_url: str = BASE_URL, politeness_window: float = POLITENESS_WINDOW
    ):
        self.base_url = base_url.rstrip("/")
        self.base_netloc = urlparse(self.base_url).netloc
        self.politeness_window = float(politeness_window)

        self.visited: set[str] = set()
        self.queue: list[str] = []
        # Stores HTML containing only in-page quote blocks (div.quote); nav/headings excluded.
        self.pages: dict[str, str] = {}

        self._last_request_ts: float | None = None

    def fetch(self, url: str) -> BeautifulSoup | None:
        """
        Fetch a URL and return BeautifulSoup (or None on failure).

        Enforces a politeness window between successive requests.
        """
        wait_for = 0.0
        now = time.time()
        if self._last_request_ts is not None:
            wait_for = self.politeness_window - (now - self._last_request_ts)
        if wait_for > 0:
            logger.debug("Politeness sleep %.2fs before %s", wait_for, url)
            time.sleep(wait_for)

        headers = {
            "User-Agent": "COMP3011-CourseworkCrawler/1.0 (+https://quotes.toscrape.com/)"
        }

        try:
            logger.debug("GET %s", url)
            resp = requests.get(url, headers=headers, timeout=15)
            self._last_request_ts = time.time()
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Request failed for %s: %s", url, e)
            return None

        return BeautifulSoup(resp.text, "html.parser")

    def extract_links(self, soup: BeautifulSoup | None, current_url: str | None = None):
        """
        Extract in-scope links from a page.

        Returns a list of normalised absolute URLs within the target site.
        """
        if soup is None:
            return []

        if current_url is None:
            current_url = self.base_url

        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if not href:
                continue

            abs_url = urljoin(current_url, href)
            norm = self._normalise_url(abs_url)
            if norm is not None:
                links.append(norm)

        # Keep deterministic order while removing duplicates
        deduped = list(dict.fromkeys(links))
        logger.debug("Extracted %d in-scope links from %s", len(deduped), current_url)
        return deduped

    @staticmethod
    def _serialise_quotes_html(soup: BeautifulSoup) -> str:
        """
        Keep only quotes.toscrape.com quote blocks (`div.quote`), not headings or nav chrome.
        """
        blocks = soup.select("div.quote")
        if not blocks:
            return "<html><body></body></html>"
        inner = "".join(str(block) for block in blocks)
        return f"<html><body>{inner}</body></html>"

    def crawl(self, url: str) -> dict[str, str]:
        """
        Crawl the target website starting from url.

        Populates self.pages (url -> HTML string of `div.quote` blocks only) and returns it.
        """
        start = self._normalise_url(url) or self.base_url

        self.visited.clear()
        self.queue = [start]
        self.pages.clear()

        logger.info("Starting crawl at %s", start)
        while self.queue:
            current = self.queue.pop(0)
            if current in self.visited:
                continue
            self.visited.add(current)

            logger.debug(
                "Crawling %s (queue=%d visited=%d)",
                current,
                len(self.queue),
                len(self.visited),
            )
            soup = self.fetch(current)
            if soup is None:
                continue

            self.pages[current] = self._serialise_quotes_html(soup)

            for link in self.extract_links(soup, current_url=current):
                if link not in self.visited:
                    self.queue.append(link)

        logger.info("Crawl complete: %d pages", len(self.pages))
        return self.pages

    def _normalise_url(self, url: str) -> str | None:
        """
        Normalise URLs and restrict crawling to the target site.
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return None

        if parsed.scheme not in ("http", "https"):
            return None

        if parsed.netloc and parsed.netloc != self.base_netloc:
            return None

        path = parsed.path or "/"
        # Drop query/fragment to avoid duplicate URLs
        normalised = f"{parsed.scheme}://{self.base_netloc}{path}"
        if (
            normalised.endswith("/")
            and normalised != f"{parsed.scheme}://{self.base_netloc}/"
        ):
            normalised = normalised.rstrip("/")
        return normalised
