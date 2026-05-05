from dataclasses import dataclass

import requests

from src.crawler import Crawler


@dataclass
class _FakeResponse:
    text: str
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_crawler(monkeypatch):
    # Deterministic, in-memory "site"
    pages_by_url = {
        "https://quotes.toscrape.com/": """
            <html><body>
              <div class="quote">
                <span class="text">“A witty saying proves nothing.”</span>
                <small class="author">Voltaire</small>
              </div>
              <a href="/page/2/">next</a>
              <a href="/about">about</a>
              <a href="https://example.com/out">external</a>
            </body></html>
        """,
        "https://quotes.toscrape.com/page/2": """
            <html><body>
              <div class="quote">
                <span class="text">“The world as we have created it is a process of our thinking.”</span>
                <small class="author">Albert Einstein</small>
              </div>
              <a href="/">home</a>
            </body></html>
        """,
        "https://quotes.toscrape.com/about": """
            <html><body>
              <h1>About</h1>
              <p>This is a test about page.</p>
            </body></html>
        """,
    }

    requested_urls: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        requested_urls.append(url)
        assert timeout == 15
        assert headers and "User-Agent" in headers
        if url not in pages_by_url:
            return _FakeResponse("not found", status_code=404)
        return _FakeResponse(pages_by_url[url], status_code=200)

    # Patch where `requests` is imported/used (src.crawler -> module attribute `requests`)
    import src.crawler as crawler_module

    monkeypatch.setattr(crawler_module.requests, "get", fake_get)

    crawler = Crawler(politeness_window=0)
    crawled = crawler.crawl("https://quotes.toscrape.com")

    # Should include only in-scope pages (no network, no external domain).
    assert set(crawled.keys()) == {
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/page/2",
        "https://quotes.toscrape.com/about",
    }
    assert all(not url.startswith("https://example.com/") for url in crawled.keys())
    assert all(not url.startswith("https://example.com/") for url in requested_urls)
    # Ensure we actually stored "quote-like" HTML content from the pages.
    assert "A witty saying proves nothing" in crawled["https://quotes.toscrape.com/"]
    assert "Albert Einstein" in crawled["https://quotes.toscrape.com/page/2"]


def test_normalize_url_restricts_to_base_site():
    crawler = Crawler(base_url="https://quotes.toscrape.com", politeness_window=0)

    assert (
        crawler._normalize_url("https://quotes.toscrape.com/tag/love/")
        == "https://quotes.toscrape.com/tag/love"
    )
    assert crawler._normalize_url("https://example.com/") is None
    assert crawler._normalize_url("mailto:test@example.com") is None
    assert crawler._normalize_url("javascript:alert(1)") is None


def test_extract_links_normalizes_and_dedupes_and_filters_out_of_scope():
    crawler = Crawler(base_url="https://quotes.toscrape.com", politeness_window=0)
    html = """
        <html><body>
          <a href="/about">about</a>
          <a href="/about#team">about-fragment</a>
          <a href="/about?x=1">about-query</a>
          <a href="https://quotes.toscrape.com/about/">about-trailing-slash</a>
          <a href="https://example.com/out">external</a>
          <a href="mailto:test@example.com">email</a>
          <a href="/about">about-duplicate</a>
        </body></html>
    """
    soup = crawler.fetch = None  # make sure we don't accidentally hit network
    # Build soup without calling crawler.fetch.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = crawler.extract_links(soup, current_url="https://quotes.toscrape.com/")

    # All the in-scope variants normalize to the same URL, and duplicates are removed.
    assert links == ["https://quotes.toscrape.com/about"]


def test_fetch_enforces_politeness_window(monkeypatch):
    import src.crawler as crawler_module

    # Simulate time progression: first request at t=100, second attempt at t=103
    # with politeness_window=6 should sleep ~3 seconds.
    times = iter([100.0, 100.0, 103.0, 106.0])

    def fake_time():
        return next(times)

    slept: list[float] = []

    def fake_sleep(seconds: float):
        slept.append(seconds)

    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse("<html></html>", status_code=200)

    monkeypatch.setattr(crawler_module.time, "time", fake_time)
    monkeypatch.setattr(crawler_module.time, "sleep", fake_sleep)
    monkeypatch.setattr(crawler_module.requests, "get", fake_get)

    crawler = Crawler(politeness_window=6)
    assert crawler.fetch("https://quotes.toscrape.com/") is not None
    assert crawler.fetch("https://quotes.toscrape.com/about") is not None

    assert slept == [3.0]


def test_fetch_returns_none_on_request_exception(monkeypatch):
    import src.crawler as crawler_module

    def fake_get(url, headers=None, timeout=None):
        raise requests.Timeout("boom")

    monkeypatch.setattr(crawler_module.requests, "get", fake_get)

    crawler = Crawler(politeness_window=0)
    assert crawler.fetch("https://quotes.toscrape.com/") is None


def test_crawl_skips_failed_pages_but_continues(monkeypatch):
    import src.crawler as crawler_module

    pages_by_url = {
        "https://quotes.toscrape.com/": """
            <html><body>
              <div class="quote">
                <span class="text">“There is nothing either good or bad, but thinking makes it so.”</span>
                <small class="author">William Shakespeare</small>
              </div>
              <a href="/about">about</a>
              <a href="/page/2/">next</a>
            </body></html>
        """,
        "https://quotes.toscrape.com/about": """
            <html><body>
              <div class="quote">
                <span class="text">“Life is what happens to us while we are making other plans.”</span>
                <small class="author">Allen Saunders</small>
              </div>
            </body></html>
        """,
        # page/2 will simulate failure (RequestException)
    }

    def fake_get(url, headers=None, timeout=None):
        if url == "https://quotes.toscrape.com/page/2":
            raise requests.ConnectionError("nope")
        if url not in pages_by_url:
            return _FakeResponse("not found", status_code=404)
        return _FakeResponse(pages_by_url[url], status_code=200)

    monkeypatch.setattr(crawler_module.requests, "get", fake_get)

    crawler = Crawler(politeness_window=0)
    crawled = crawler.crawl("https://quotes.toscrape.com/")

    assert set(crawled.keys()) == {
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/about",
    }
    # Quote content should still be retained for successfully crawled pages.
    assert "thinking makes it so" in crawled["https://quotes.toscrape.com/"]
    assert "Allen Saunders" in crawled["https://quotes.toscrape.com/about"]