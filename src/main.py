from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
import sys

try:
    # Works when executed as a module: `python -m src.main`
    from src.crawler import BASE_URL, POLITENESS_WINDOW, Crawler
    from src.indexer import Indexer
    from src.logging_utils import configure_logging
    from src.search import find_pages
except ModuleNotFoundError:
    # Works when executed as a script: `python src/main.py`
    _SRC_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(_SRC_DIR))
    from crawler import BASE_URL, POLITENESS_WINDOW, Crawler  # type: ignore[no-redef]
    from indexer import Indexer  # type: ignore[no-redef]
    from logging_utils import configure_logging  # type: ignore[no-redef]
    from search import find_pages  # type: ignore[no-redef]


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


def parse_startup_args(argv: list[str] | None) -> argparse.Namespace:
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
    parser.add_argument(
        "--start-url",
        default=BASE_URL,
        help="URL to start crawling from (used by the 'build' command).",
    )
    parser.add_argument(
        "--politeness-window",
        type=float,
        default=POLITENESS_WINDOW,
        help="Seconds between successive requests (used by 'build').",
    )
    return parser.parse_args(argv)


def run_shell(
    *,
    index_path: Path,
    start_url: str = BASE_URL,
    politeness_window: float = POLITENESS_WINDOW,
) -> int:
    indexer: Indexer | None = None
    index_path = Path(index_path)

    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0

        try:
            parts = shlex.split(line, comments=False)
        except ValueError as e:
            print(e, file=sys.stderr)
            continue

        if not parts:
            continue

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("exit", "quit"):
            return 0

        if cmd == "build":
            indexer = build_index(
                start_url=start_url,
                index_path=index_path,
                politeness_window=politeness_window,
            )
            continue

        if cmd == "load":
            if not index_path.is_file():
                print(
                    f"No index file at {index_path}. Run 'build' first.",
                    file=sys.stderr,
                )
                continue
            try:
                indexer = load_index(index_path=index_path)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"Failed to load index: {e}", file=sys.stderr)
                indexer = None
            continue

        if cmd == "print":
            if indexer is None:
                print(
                    "No index in memory. Run 'build' or 'load' first.", file=sys.stderr
                )
                continue
            if len(args) != 1:
                print("Usage: print <word>", file=sys.stderr)
                continue
            term = args[0]
            postings = indexer.get(term)
            print(
                json.dumps(
                    {url: p.to_dict() for url, p in postings.items()},
                    indent=2,
                    sort_keys=True,
                )
            )
            continue

        if cmd == "find":
            if indexer is None:
                print(
                    "No index in memory. Run 'build' or 'load' first.", file=sys.stderr
                )
                continue
            urls = find_pages(indexer, args)
            for url in urls:
                print(url)
            continue

        print(f"Unknown command: {parts[0]!r}", file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ns = parse_startup_args(argv)
    configure_logging(verbose=ns.verbose, quiet=ns.quiet)
    return run_shell(
        index_path=Path(ns.index_path),
        start_url=ns.start_url,
        politeness_window=ns.politeness_window,
    )


if __name__ == "__main__":
    raise SystemExit(main())
