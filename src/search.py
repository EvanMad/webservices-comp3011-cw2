from __future__ import annotations

from collections.abc import Iterable

from .indexer import Indexer

"""
Search helpers for the COMP3011 coursework tool.

## Inverted index data structure

The in-memory index (and the on-disk JSON file) is conceptually:

- term -> url -> posting
- posting stores:
  - count: term frequency within that page
  - positions: 0-based token positions where the term occurs in that page

In code this is represented as:

- Indexer.index: dict[str, dict[str, Posting]]
"""


def find_pages(indexer: Indexer, query_terms: Iterable[str]) -> list[str]:
    """
    Return URLs that contain every query term (boolean AND).

    Terms need not be adjacent; each normalized term must appear at least once
    on the page. Results are returned in deterministic (sorted) order.
    """
    terms = [Indexer.normalize_term(t) for t in query_terms if t.strip()]
    if not terms:
        return []

    urls = set(indexer.get(terms[0]).keys())
    for t in terms[1:]:
        urls &= set(indexer.get(t).keys())

    return sorted(urls)
