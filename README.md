# Project overview

This project implements a small search engine tool. The interface is as a command-line search tool: a crawler fetches pages from [quotes.toscrape.com](https://quotes.toscrape.com/), an indexer builds an inverted index of word occurrences across those pages, and search commands let you inspect the index and find URLs that match single- or multi-word queries. The purpose is to demonstrate how crawling, indexing, and retrieval fit together in a minimal search engine, with the index persisted to disk so it can be rebuilt or loaded without recrawling every session.

# Architecture

The program is split into four layers: crawl, index, search, and an interactive shell that allows a user to interact.

**Crawler (`src/crawler.py`)**  
The `Crawler` class walks the target site with a breadth-first queue. Each HTTP GET goes through a configurable politeness delay (default six seconds) between requests. URLs are normalised and limited to the same host as the configured base URL; off-site links are ignored. Successful responses are parsed with Beautiful Soup; the crawler stores each page as HTML keyed by URL. The fetch path retries transient network errors and some gateway status codes with backoff.

**Indexer (`src/indexer.py`)**  
The `Indexer` class turns stored HTML into tokens: scripts, styles, and similar tags are stripped, visible text is extracted, and words are matched with a regular expression then case-folded for case-insensitive lookup. It builds an inverted index mapping each term to a map of URLs to `Posting` records (term frequency in that page and zero-based token positions). Document token counts per URL are kept in `doc_lengths` for ranking. The whole structure serialises to a single JSON file and can be rehydrated with `load`.

**Search (`src/search.py`)**  
Query strings are tokenised with the same rules as indexing. `find` resolves to URLs that contain every query term (boolean AND across terms). Matching documents are ordered by a BM25-style score summed over query terms (Okapi BM25 parameters), with ties broken by URL. A scored variant exists for the shell output; `print` reads postings for one term directly from the index.

**CLI shell (`src/main.py`)**  
Startup uses `argparse` for logging verbosity, index path, crawl start URL, and politeness window. The program then enters a read-eval loop on standard input, splitting each line with `shlex` so quoted arguments behave predictably. Commands are `build` (crawl, index, write JSON), `load` (read JSON into memory), `print <term>` (JSON postings for that term), and `find <term> [...]` (AND search with scores). `exit` or `quit` ends the session; `build` and `load` replace the in-memory indexer used by `print` and `find`.

# Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13 or newer (see `pyproject.toml`).

From the repository root install the dependencies:

```bash
uv sync
```

To run the interactive shell:

```bash
uv run search-engine-tool
```

Optional flags (before the shell starts): `--index-path`, `--start-url`, `--politeness-window`, `-v` / `-q` for logging.

# Usage

Start the shell (see Installation), then type commands at the `>` prompt.

**`build`** — crawl the site, build the index, write `data/index.json` (slow by design because of the politeness delay):

```text
> build
```

**`load`** — read the saved index from disk into memory (use after a previous `build`, or in a new session):

```text
> load
```

**`print`** — show inverted-index postings for one word as JSON (`count` and `positions` per URL):

```text
> print nonsense
```

**`find`** — list pages that contain every given term (boolean AND), one line per URL with a BM25-style score:

```text
> find indifference
> find good friends
```

Leave the shell with `exit` or `quit`.

# Testing

To run the testing suite:

```bash
make test
```

or for optional test coverage:

```bash
make coverage
```

Testing is ran automatically pre-merge in Github Actions.

# Linting & Formatting

This project can be linted and formated with [Ruff](https://docs.astral.sh/ruff/) with the following commands:

```bash
make lint
```

```bash
make format
```

These are also automatically ran pre-merge as part of the CI/CD pipeline implemented in Github Actions.

# Dependencies

Declared in `pyproject.toml`; `requirements.txt` contains a snapshot of the full tree if you wish to install without uv. This was generated with `uv pip compile` and `pyproject.toml` is the source-of-truth for dependencies for this project.

The primary dependencies used in this project are:
- **requests** — HTTP client for the crawler  
- **beautifulsoup4** — HTML parsing in the crawler and indexer  
- **pytest** — tests (`make test`)  
- **pytest-cov** — coverage (`make coverage`)