from __future__ import annotations

import pytest

from src.indexer import Indexer
from src.search import find_pages


@pytest.fixture()
def pages_by_url() -> dict[str, str]:
    return {
        "https://quotes.toscrape.com/": """
            <html><body>
              <div class="quote">
                <span class="text">Good friends, good books, and a sleepy conscience.</span>
              </div>
            </body></html>
        """,
        "https://quotes.toscrape.com/about": """
            <html><body>
              <p>This page is about testing.</p>
            </body></html>
        """,
    }


@pytest.fixture()
def indexer(pages_by_url: dict[str, str]) -> Indexer:
    idx = Indexer()
    idx.build(pages_by_url)
    return idx


def test_find_pages_empty_query_returns_empty(indexer: Indexer):
    assert find_pages(indexer, []) == []
    assert find_pages(indexer, ["", "   "]) == []


def test_find_pages_single_term(indexer: Indexer):
    assert find_pages(indexer, ["friends"]) == ["https://quotes.toscrape.com/"]


def test_find_pages_two_terms_and_anywhere(indexer: Indexer):
    # Brief-style: both "good" and "friends" appear on the home page.
    assert find_pages(indexer, ["good", "friends"]) == ["https://quotes.toscrape.com/"]


def test_find_pages_two_terms_and_other_page(indexer: Indexer):
    assert find_pages(indexer, ["page", "is"]) == ["https://quotes.toscrape.com/about"]


def test_find_pages_non_adjacent_terms_still_match(indexer: Indexer):
    # Both words on the home page, not next to each other in the token stream.
    assert find_pages(indexer, ["friends", "books"]) == ["https://quotes.toscrape.com/"]
