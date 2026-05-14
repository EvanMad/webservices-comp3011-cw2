import logging
import time
from collections import deque
from typing import Callable

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE_URL = "https://quotes.toscrape.com"
POLITENESS_WINDOW = 6  # seconds
# (connect, read) — fail fast on dead hosts, allow slow responses.
REQUEST_TIMEOUT = (5.0, 20.0)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0
# Retry these server-side failures that often clear on a new connection.
RETRYABLE_HTTP_STATUS = frozenset({502, 503, 504})

logger = logging.getLogger(__name__)


def _default_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {"User-Agent": "COMP3011-CourseworkCrawler/1.0 (+https://quotes.toscrape.com/)"}
    )
    return s


class Crawler:
    def __init__(
        self,
        base_url: str = BASE_URL,
        politeness_window: float = POLITENESS_WINDOW,
        *,
        session: requests.Session | None = None,
        request_timeout: float | tuple[float, float] = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        retry_backoff_base: float = RETRY_BACKOFF_BASE,
        sleep_fn: Callable[[float], None] | None = None,
        time_fn: Callable[[], float] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.base_netloc = urlparse(self.base_url).netloc
        self.politeness_window = float(politeness_window)
        self._session = session if session is not None else _default_session()
        self.request_timeout = request_timeout
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_base = float(retry_backoff_base)
        self._sleep = sleep_fn or time.sleep
        self._time = time_fn or time.time

        self.visited: set[str] = set()
        self.queue: deque[str] = deque()
        # Stores raw HTML by URL; indexer can parse/tokenise as needed.
        self.pages: dict[str, str] = {}

        self._last_request_ts: float | None = None

    @staticmethod
    def _is_transient_request_error(exc: BaseException) -> bool:
        return isinstance(exc, (Timeout, ConnectionError, ChunkedEncodingError))

    def _politeness_sleep(self, url: str) -> None:
        now = self._time()
        if self._last_request_ts is not None:
            wait_for = self.politeness_window - (now - self._last_request_ts)
            if wait_for > 0:
                logger.debug("Politeness sleep %.2fs before %s", wait_for, url)
                self._sleep(wait_for)

    def fetch(self, url: str) -> BeautifulSoup | None:
        """
        Fetch a URL and return BeautifulSoup (or None on failure).

        Enforces a politeness window before the first attempt. Retries transient
        network failures and common gateway errors with exponential backoff.
        """
        self._politeness_sleep(url)

        for attempt in range(self.max_retries):
            if attempt > 0:
                delay = self.retry_backoff_base * (2 ** (attempt - 1))
                logger.info(
                    "Retry %d/%d for %s after %.1fs",
                    attempt + 1,
                    self.max_retries,
                    url,
                    delay,
                )
                self._sleep(delay)

            try:
                logger.debug("GET %s (attempt %d)", url, attempt + 1)
                resp = self._session.get(url, timeout=self.request_timeout)
                self._last_request_ts = self._time()
            except requests.RequestException as e:
                self._last_request_ts = self._time()
                logger.warning(
                    "Request failed for %s (attempt %d/%d): %s",
                    url,
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt + 1 < self.max_retries and self._is_transient_request_error(
                    e
                ):
                    continue
                return None

            if (
                resp.status_code in RETRYABLE_HTTP_STATUS
                and attempt + 1 < self.max_retries
            ):
                logger.warning(
                    "HTTP %s for %s; retrying (%d/%d)",
                    resp.status_code,
                    url,
                    attempt + 1,
                    self.max_retries,
                )
                continue

            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                logger.warning("HTTP error for %s: %s", url, e)
                return None

            return BeautifulSoup(resp.text, "html.parser")

        return None

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

    def crawl(self, url: str) -> dict[str, str]:
        """
        Crawl the target website starting from url.

        Populates self.pages (url -> html) and returns it.
        """
        start = self._normalise_url(url) or self.base_url

        self.visited.clear()
        self.queue = deque([start])
        self.pages.clear()

        logger.info("Starting crawl at %s", start)
        while self.queue:
            current = self.queue.popleft()
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

            self.pages[current] = str(soup)

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
