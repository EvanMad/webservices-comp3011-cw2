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


def _query_tokens(fragments: Iterable[str]) -> list[str]:
    """
    Turn raw query fragments into index keys using the same rules as indexing.

    Non-string fragments are skipped. Whitespace-only and punctuation-only
    pieces yield no tokens. Duplicates are removed while preserving order so
    boolean AND does not repeat work.
    """
    out: list[str] = []
    for fragment in fragments:
        if not isinstance(fragment, str):
            continue
        out.extend(Indexer.tokenise_text(fragment))
    return list(dict.fromkeys(out))


def find_pages(indexer: Indexer, query_terms: Iterable[str]) -> list[str]:
    """
    Return URLs that contain every query term (boolean AND).

    Each shell argument may contain several words, punctuation, or hyphenated
    pieces; they are split with `Indexer.tokenise_text`, matching how pages
    were indexed. Terms need not be adjacent on the page. Results are sorted
    for a stable order.
    """
    terms = _query_tokens(query_terms)
    if not terms:
        return []

    urls = set(indexer.get(terms[0]).keys())
    for t in terms[1:]:
        urls &= set(indexer.get(t).keys())

    return sorted(urls)
