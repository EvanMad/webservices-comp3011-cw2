from __future__ import annotations

from collections.abc import Iterable

from .indexer import Indexer, Posting

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
    Return URLs that contain the query phrase.

    - For a single term, this returns all URLs containing that term.
    - For multiple terms, this returns URLs where the terms occur consecutively
      in the token stream (i.e., a phrase match using postings' positions).

    Results are returned in deterministic (sorted) order.
    """
    terms = [Indexer.normalize_term(t) for t in query_terms if t.strip()]
    if not terms:
        return []

    postings_by_term: list[dict[str, Posting]] = [indexer.get(t) for t in terms]
    urls = set(postings_by_term[0].keys())
    for p in postings_by_term[1:]:
        urls &= set(p.keys())

    if len(terms) == 1:
        return sorted(urls)

    def matches_phrase(url: str) -> bool:
        # A phrase match exists if there is a starting position p such that
        # p+i is present in the positions list for the i-th term.
        first_positions = postings_by_term[0][url].positions
        position_sets = [set(p[url].positions) for p in postings_by_term[1:]]
        for start in first_positions:
            if all((start + i + 1) in s for i, s in enumerate(position_sets)):
                return True
        return False

    return sorted([u for u in urls if matches_phrase(u)])
