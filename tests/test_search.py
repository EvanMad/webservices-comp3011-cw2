from __future__ import annotations

from typing import Any

import pytest

from src.indexer import Indexer
from src.search import find_pages, find_pages_scored


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


def test_find_pages_boolean_and_excludes_partial_matches(indexer: Indexer):
    assert find_pages(indexer, ["friends", "nope"]) == []


def test_find_pages_punctuation_on_term_still_matches(indexer: Indexer):
    assert find_pages(indexer, ["friends,"]) == ["https://quotes.toscrape.com/"]
    assert find_pages(indexer, ['"friends"']) == ["https://quotes.toscrape.com/"]


def test_find_pages_one_fragment_with_multiple_words(indexer: Indexer):
    assert find_pages(indexer, ["good friends"]) == ["https://quotes.toscrape.com/"]


def test_find_pages_hyphen_splits_like_indexing(indexer: Indexer):
    assert find_pages(indexer, ["good-friends"]) == ["https://quotes.toscrape.com/"]


def test_find_pages_non_string_fragments_skipped(indexer: Indexer):
    mixed: tuple[Any, ...] = ("good", None, "friends")
    assert find_pages(indexer, mixed) == ["https://quotes.toscrape.com/"]


def test_find_pages_duplicate_words_deduped(indexer: Indexer):
    assert find_pages(indexer, ["good", "good", "friends"]) == [
        "https://quotes.toscrape.com/"
    ]


def test_find_pages_only_punctuation_or_whitespace(indexer: Indexer):
    assert find_pages(indexer, ["...", "   ", "---"]) == []


def test_find_pages_ranked_by_bm25_heavier_page_first():
    """Both URLs match AND; the page with higher term counts should rank first."""
    pages = {
        "https://a.example/": "<html><body>alpha beta gamma</body></html>",
        "https://b.example/": "<html><body>alpha alpha alpha beta beta</body></html>",
    }
    idx = Indexer()
    idx.build(pages)
    assert find_pages(idx, ["alpha", "beta"]) == [
        "https://b.example/",
        "https://a.example/",
    ]
    scores = [s for _, s in find_pages_scored(idx, ["alpha", "beta"])]
    assert scores == sorted(scores, reverse=True)
