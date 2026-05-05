from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup


_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.IGNORECASE)


@dataclass(slots=True)
class Posting:
    """
    Statistics for a single term in a single page.

    - `count`: term frequency within the page.
    - `positions`: 0-based positions in the page token stream.
    """

    count: int
    positions: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "positions": self.positions}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Posting":
        positions = data.get("positions", [])
        if not isinstance(positions, list):
            raise TypeError("posting.positions must be a list")
        return cls(
            count=int(data.get("count", len(positions))),
            positions=[int(p) for p in positions],
        )


class Indexer:
    """
    Build and persist an inverted index over crawled HTML pages.

    The index structure is:

        term -> url -> Posting(count, positions)
    """

    def __init__(self) -> None:
        self.index: dict[str, dict[str, Posting]] = {}

    def clear(self) -> None:
        self.index.clear()

    def add_page(self, url: str, html: str) -> None:
        tokens = list(self.tokenize_html(html))
        for pos, term in enumerate(tokens):
            postings = self.index.setdefault(term, {})
            posting = postings.get(url)
            if posting is None:
                postings[url] = Posting(count=1, positions=[pos])
            else:
                posting.count += 1
                posting.positions.append(pos)

    def build(self, pages_by_url: dict[str, str]) -> dict[str, dict[str, Posting]]:
        """
        Build an index from a mapping of url -> html.

        Returns the internal index for convenience.
        """
        self.clear()
        for url, html in pages_by_url.items():
            print(f"Adding page: {url}")
            self.add_page(url, html)
        return self.index

    def get(self, term: str) -> dict[str, Posting]:
        """Return postings for a term (case-insensitive)."""
        return self.index.get(self.normalize_term(term), {})

    @staticmethod
    def normalize_term(term: str) -> str:
        return term.casefold()

    @classmethod
    def tokenize_text(cls, text: str) -> Iterable[str]:
        for m in _WORD_RE.finditer(text):
            yield m.group(0).casefold()

    @classmethod
    def tokenize_html(cls, html: str) -> Iterable[str]:
        soup = BeautifulSoup(html, "html.parser")

        # Remove non-visible / non-content text.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        return cls.tokenize_text(text)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to a JSON-serializable representation.
        """
        return {
            "index": {
                term: {url: posting.to_dict() for url, posting in postings.items()}
                for term, postings in self.index.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Indexer":
        raw_index = data.get("index", {})
        if not isinstance(raw_index, dict):
            raise TypeError("index must be a dict")

        inst = cls()
        for term, postings in raw_index.items():
            if not isinstance(postings, dict):
                continue
            inst.index[str(term)] = {
                str(url): Posting.from_dict(p) for url, p in postings.items()
            }
        return inst

    def save(self, path: str) -> None:
        """
        Save the index to a single JSON file.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path: str) -> "Indexer":
        """
        Load the index from a JSON file created by `save`.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise TypeError("index file root must be a JSON object")
        return cls.from_dict(data)
