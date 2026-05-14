from dataclasses import dataclass

import requests

from src.crawler import REQUEST_TIMEOUT, Crawler


@dataclass
class _FakeResponse:
    text: str
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _StubSession:
    """Minimal session stand-in (tests avoid patching requests internals)."""

    def __init__(self, get_impl):
        self.headers = {}
        self._get_impl = get_impl

    def get(self, url, headers=None, timeout=None):
        return self._get_impl(url, headers, timeout)


def test_crawler():
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
        assert timeout == REQUEST_TIMEOUT
        if url not in pages_by_url:
            return _FakeResponse("not found", status_code=404)
        return _FakeResponse(pages_by_url[url], status_code=200)

    crawler = Crawler(
        politeness_window=0, session=_StubSession(fake_get), max_retries=1
    )
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


def test_normalise_url_restricts_to_base_site():
    crawler = Crawler(base_url="https://quotes.toscrape.com", politeness_window=0)

    assert (
        crawler._normalise_url("https://quotes.toscrape.com/tag/love/")
        == "https://quotes.toscrape.com/tag/love"
    )
    assert crawler._normalise_url("https://example.com/") is None
    assert crawler._normalise_url("mailto:test@example.com") is None
    assert crawler._normalise_url("javascript:alert(1)") is None


def test_extract_links_normalises_and_dedupes_and_filters_out_of_scope():
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
    # Build soup without calling crawler.fetch.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = crawler.extract_links(soup, current_url="https://quotes.toscrape.com/")

    # All the in-scope variants normalise to the same URL, and duplicates are removed.
    assert links == ["https://quotes.toscrape.com/about"]


def test_fetch_enforces_politeness_window():
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

    crawler = Crawler(
        politeness_window=6,
        session=_StubSession(fake_get),
        max_retries=1,
        sleep_fn=fake_sleep,
        time_fn=fake_time,
    )
    assert crawler.fetch("https://quotes.toscrape.com/") is not None
    assert crawler.fetch("https://quotes.toscrape.com/about") is not None

    assert slept == [3.0]


def test_fetch_returns_none_on_request_exception():
    def fake_get(url, headers=None, timeout=None):
        raise requests.Timeout("boom")

    crawler = Crawler(
        politeness_window=0, session=_StubSession(fake_get), max_retries=1
    )
    assert crawler.fetch("https://quotes.toscrape.com/") is None


def test_fetch_retries_transient_error_then_succeeds():
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise requests.ConnectionError("nope")
        return _FakeResponse("<html><body>ok</body></html>", status_code=200)

    slept: list[float] = []

    crawler = Crawler(
        politeness_window=0,
        session=_StubSession(fake_get),
        max_retries=3,
        retry_backoff_base=0.5,
        sleep_fn=lambda s: slept.append(s),
    )
    soup = crawler.fetch("https://quotes.toscrape.com/")
    assert soup is not None
    assert "ok" in str(soup)
    assert calls["n"] == 2
    assert slept == [0.5]


def test_fetch_retries_transient_http_then_succeeds():
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse("bad gateway", status_code=502)
        return _FakeResponse("<html><body>ok</body></html>", status_code=200)

    crawler = Crawler(
        politeness_window=0,
        session=_StubSession(fake_get),
        max_retries=3,
        retry_backoff_base=0.0,
        sleep_fn=lambda s: None,
    )
    soup = crawler.fetch("https://quotes.toscrape.com/")
    assert soup is not None
    assert calls["n"] == 2


def test_extract_links_none_soup_returns_empty():
    crawler = Crawler(politeness_window=0)
    assert crawler.extract_links(None) == []


def test_extract_links_uses_base_url_when_current_url_missing():
    crawler = Crawler(base_url="https://quotes.toscrape.com", politeness_window=0)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        '<html><body><a href="/about">x</a></body></html>', "html.parser"
    )
    assert crawler.extract_links(soup, current_url=None) == [
        "https://quotes.toscrape.com/about"
    ]


def test_extract_links_skips_empty_href():
    crawler = Crawler(base_url="https://quotes.toscrape.com", politeness_window=0)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        '<html><body><a href="">empty</a><a href="/tag/x">ok</a></body></html>',
        "html.parser",
    )
    assert crawler.extract_links(soup, current_url="https://quotes.toscrape.com/") == [
        "https://quotes.toscrape.com/tag/x"
    ]


def test_crawl_skips_already_visited_when_url_queued_twice():
    # Two branches both link to /target before /target is visited, so /target
    # appears twice in the FIFO queue; the second dequeue hits `visited`.
    pages_by_url = {
        "https://quotes.toscrape.com/": """
            <html><body>
              <a href="/left">left</a>
              <a href="/right">right</a>
            </body></html>
        """,
        "https://quotes.toscrape.com/left": """
            <html><body>
              <a href="/target">t1</a>
            </body></html>
        """,
        "https://quotes.toscrape.com/right": """
            <html><body>
              <a href="/target">t2</a>
            </body></html>
        """,
        "https://quotes.toscrape.com/target": """
            <html><body><p>done</p></body></html>
        """,
    }

    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(pages_by_url[url], status_code=200)

    crawler = Crawler(
        politeness_window=0, session=_StubSession(fake_get), max_retries=1
    )
    crawled = crawler.crawl("https://quotes.toscrape.com/")
    assert set(crawled) == {
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/left",
        "https://quotes.toscrape.com/right",
        "https://quotes.toscrape.com/target",
    }


def test_normalise_url_returns_none_when_urlparse_raises(monkeypatch):
    import src.crawler as crawler_module

    crawler = Crawler(politeness_window=0)

    def bad_urlparse(url):
        raise ValueError("bad")

    monkeypatch.setattr(crawler_module, "urlparse", bad_urlparse)
    assert crawler._normalise_url("https://quotes.toscrape.com/") is None


def test_fetch_returns_none_on_http_error():
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse("gone", status_code=404)

    crawler = Crawler(
        politeness_window=0, session=_StubSession(fake_get), max_retries=1
    )
    assert crawler.fetch("https://quotes.toscrape.com/missing") is None


def test_crawl_skips_failed_pages_but_continues():
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

    crawler = Crawler(
        politeness_window=0, session=_StubSession(fake_get), max_retries=1
    )
    crawled = crawler.crawl("https://quotes.toscrape.com/")

    assert set(crawled.keys()) == {
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/about",
    }
    # Quote content should still be retained for successfully crawled pages.
    assert "thinking makes it so" in crawled["https://quotes.toscrape.com/"]
    assert "Allen Saunders" in crawled["https://quotes.toscrape.com/about"]


def test_default_session_has_user_agent():
    crawler = Crawler(politeness_window=0)
    assert "User-Agent" in crawler._session.headers


def test_max_retries_coerced_to_at_least_one():
    c = Crawler(politeness_window=0, max_retries=0)
    assert c.max_retries == 1
