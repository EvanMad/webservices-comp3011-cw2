from __future__ import annotations

from collections.abc import Iterable
import math

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

## Ranking

`find_pages` / `find_pages_scored` use boolean AND, then **BM25** (Okapi-style)
per query term, summed: length-normalised term frequency with the usual BM25
IDF. Document length is the page token count (stored in ``Indexer.doc_lengths``,
or inferred when loading older index files by summing posting counts per URL).
Constants ``k1 = 1.2`` and ``b = 0.75``. Ties break by URL ascending.
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


def _corpus_document_count(indexer: Indexer) -> int:
    if indexer.doc_lengths:
        return len(indexer.doc_lengths)
    urls: set[str] = set()
    for postings in indexer.index.values():
        urls.update(postings)
    return len(urls)


_K1 = 1.2
_B = 0.75


def _avg_doc_length(indexer: Indexer) -> float:
    if not indexer.doc_lengths:
        return 1.0
    total = sum(indexer.doc_lengths.values())
    return total / len(indexer.doc_lengths) if total > 0 else 1.0


def _idf_bm25(num_documents: int, doc_freq: int) -> float:
    return math.log((num_documents - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)


def _doc_length(indexer: Indexer, url: str) -> int:
    n = indexer.doc_lengths.get(url)
    if n is not None and n > 0:
        return n
    # Fallback if a URL appears only in a partial / legacy index.
    return (
        sum(
            postings[url].count
            for postings in indexer.index.values()
            if url in postings
        )
        or 1
    )


def _bm25_sum(
    indexer: Indexer,
    url: str,
    terms: list[str],
    num_documents: int,
    avgdl: float,
) -> float:
    doc_len = _doc_length(indexer, url)
    norm = _K1 * (1.0 - _B + _B * (doc_len / avgdl))
    total = 0.0
    for term in terms:
        posting = indexer.get(term)[url]
        f = posting.count
        df = len(indexer.get(term))
        idf = _idf_bm25(num_documents, df)
        denom = f + norm
        total += idf * (f * (_K1 + 1.0)) / denom
    return total


def find_pages_scored(
    indexer: Indexer, query_terms: Iterable[str]
) -> list[tuple[str, float]]:
    """
    Like `find_pages`, but each result is ``(url, bm25_score)`` with scores
    descending (ties by URL ascending).
    """
    terms = _query_tokens(query_terms)
    if not terms:
        return []

    urls = set(indexer.get(terms[0]).keys())
    for t in terms[1:]:
        urls &= set(indexer.get(t).keys())

    if not urls:
        return []

    n = _corpus_document_count(indexer)
    if n == 0:
        return [(u, 0.0) for u in sorted(urls)]

    avgdl = _avg_doc_length(indexer)
    scored = [(u, _bm25_sum(indexer, u, terms, n, avgdl)) for u in urls]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def find_pages(indexer: Indexer, query_terms: Iterable[str]) -> list[str]:
    """
    Return URLs that contain every query term (boolean AND), ranked by BM25.

    Each shell argument may contain several words, punctuation, or hyphenated
    pieces; they are split with `Indexer.tokenise_text`, matching how pages
    were indexed. Terms need not be adjacent on the page. Higher BM25 scores
    rank first; equal scores sort by URL for a stable order.
    """
    return [url for url, _ in find_pages_scored(indexer, query_terms)]
