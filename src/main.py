from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

try:
    # Works when executed as a module: `python -m src.main`
    from src.crawler import BASE_URL, POLITENESS_WINDOW, Crawler
    from src.indexer import Indexer, Posting
    from src.logging_utils import configure_logging
except ModuleNotFoundError:
    # Works when executed as a script: `python src/main.py`
    _SRC_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(_SRC_DIR))
    from crawler import BASE_URL, POLITENESS_WINDOW, Crawler  # type: ignore[no-redef]
    from indexer import Indexer, Posting  # type: ignore[no-redef]
    from logging_utils import configure_logging  # type: ignore[no-redef]


DEFAULT_INDEX_PATH = Path("data/index.json")


def build_index(
    *,
    start_url: str = BASE_URL,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    politeness_window: float = POLITENESS_WINDOW,
) -> Indexer:
    """
    Crawl from `start_url`, build an inverted index, and save it to `index_path`.
    """
    crawler = Crawler(base_url=BASE_URL, politeness_window=politeness_window)
    pages_by_url = crawler.crawl(start_url)

    indexer = Indexer()
    indexer.build(pages_by_url)

    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    indexer.save(str(index_path))
    return indexer


def load_index(*, index_path: str | Path = DEFAULT_INDEX_PATH) -> Indexer:
    return Indexer.load(str(index_path))


def find_pages(indexer: Indexer, query_terms: Iterable[str]) -> list[str]:
    """
    Return URLs that contain *all* query terms, sorted by a simple score.

    Score is the sum of term frequencies across all query terms.
    """
    terms = [Indexer.normalize_term(t) for t in query_terms if t.strip()]
    if not terms:
        return []

    postings_by_term: list[dict[str, Posting]] = [indexer.get(t) for t in terms]
    urls = set(postings_by_term[0].keys())
    for p in postings_by_term[1:]:
        urls &= set(p.keys())

    def score(url: str) -> int:
        return sum(
            p.get(url, Posting(count=0, positions=[])).count for p in postings_by_term
        )

    return sorted(urls, key=lambda u: (-score(u), u))


def _cmd_build(args: argparse.Namespace) -> int:
    build_index(
        start_url=args.start_url,
        index_path=args.index_path,
        politeness_window=args.politeness_window,
    )
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    _ = load_index(index_path=args.index_path)
    return 0


def _cmd_print(args: argparse.Namespace) -> int:
    indexer = load_index(index_path=args.index_path)
    postings = indexer.get(args.term)
    print(
        json.dumps(
            {url: p.to_dict() for url, p in postings.items()}, indent=2, sort_keys=True
        )
    )
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    indexer = load_index(index_path=args.index_path)
    urls = find_pages(indexer, args.terms)
    for url in urls:
        print(url)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="search-tool")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (repeatable).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Decrease logging verbosity (repeatable).",
    )
    parser.add_argument(
        "--index-path",
        default=str(DEFAULT_INDEX_PATH),
        help="Path to the index file (JSON).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Crawl, build index, and save it.")
    p_build.add_argument(
        "--start-url", default=BASE_URL, help="URL to start crawling from."
    )
    p_build.add_argument(
        "--politeness-window",
        type=float,
        default=POLITENESS_WINDOW,
        help="Seconds between successive requests.",
    )
    p_build.set_defaults(func=_cmd_build)

    p_load = sub.add_parser("load", help="Load an existing index (validates it).")
    p_load.set_defaults(func=_cmd_load)

    p_print = sub.add_parser("print", help="Print the inverted index for a word.")
    p_print.add_argument("term")
    p_print.set_defaults(func=_cmd_print)

    p_find = sub.add_parser("find", help="Find pages containing all query terms.")
    p_find.add_argument("terms", nargs="*")
    p_find.set_defaults(func=_cmd_find)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
