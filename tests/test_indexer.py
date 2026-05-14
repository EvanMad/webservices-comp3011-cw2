from __future__ import annotations

from pathlib import Path

import pytest

from src.indexer import Indexer, Posting


@pytest.fixture()
def pages_by_url() -> dict[str, str]:
    return {
        "https://quotes.toscrape.com/": """
            <html><head>
              <style>.hidden { display:none; }</style>
              <script>var secret = "dont index me";</script>
            </head><body>
              <h1>Home</h1>
              <div class="quote">
                <span class="text">“Good friends, good books, and a sleepy conscience.”</span>
                <small class="author">Mark Twain</small>
              </div>
              <p>GOOD good Good.</p>
            </body></html>
        """,
        "https://quotes.toscrape.com/about": """
            <html><body>
              <h1>About</h1>
              <p>This page is about testing.</p>
              <noscript>Should not be indexed</noscript>
            </body></html>
        """,
    }


def test_tokenise_html_case_insensitive_and_strips_non_content(
    pages_by_url: dict[str, str],
):
    tokens = list(Indexer.tokenise_html(pages_by_url["https://quotes.toscrape.com/"]))

    # Visible content words exist.
    assert "good" in tokens
    assert "friends" in tokens
    assert "mark" in tokens

    # Script/style content should not be indexed.
    assert "secret" not in tokens
    assert "dont" not in tokens
    assert "index" not in tokens


def test_add_page_creates_posting_with_count_and_positions():
    indexer = Indexer()
    html = "<html><body>Good good, GOOD!</body></html>"
    indexer.add_page("u1", html)

    postings = indexer.get("good")
    assert set(postings.keys()) == {"u1"}
    posting = postings["u1"]
    assert posting.count == 3
    assert posting.positions == [0, 1, 2]


def test_build_indexes_multiple_pages(pages_by_url: dict[str, str]):
    indexer = Indexer()
    indexer.build(pages_by_url)

    # 'about' appears on both pages (Home quote includes "good books" etc; About page includes "about").
    # Ensure we can retrieve postings and they have the expected shape.
    about_postings = indexer.get("about")
    assert "https://quotes.toscrape.com/about" in about_postings
    assert isinstance(about_postings["https://quotes.toscrape.com/about"], Posting)

    # 'twain' only appears on home page.
    twain_postings = indexer.get("twain")
    assert set(twain_postings.keys()) == {"https://quotes.toscrape.com/"}
    assert twain_postings["https://quotes.toscrape.com/"].count == 1


def test_get_is_case_insensitive(pages_by_url: dict[str, str]):
    indexer = Indexer()
    indexer.build(pages_by_url)

    assert indexer.get("GOOD") == indexer.get("good")


def test_posting_from_dict_rejects_non_list_positions():
    with pytest.raises(TypeError, match="posting.positions must be a list"):
        Posting.from_dict({"count": 1, "positions": "nope"})


def test_indexer_from_dict_requires_dict_index():
    with pytest.raises(TypeError, match="index must be a dict"):
        Indexer.from_dict({"index": []})


def test_indexer_from_dict_skips_non_dict_posting_maps():
    data = {
        "index": {
            "hello": "not-a-dict",
            "world": {"https://x/": {"count": 1, "positions": [0]}},
        }
    }
    idx = Indexer.from_dict(data)
    assert idx.get("hello") == {}
    assert idx.get("world")


def test_indexer_from_dict_without_doc_lengths_recomputes_lengths():
    idx = Indexer.from_dict(
        {
            "index": {
                "alpha": {"https://u/": {"count": 2, "positions": [0, 2]}},
                "beta": {"https://u/": {"count": 1, "positions": [1]}},
            }
        }
    )
    assert idx.doc_lengths == {"https://u/": 3}


def test_indexer_load_rejects_non_object_root(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("42", encoding="utf-8")
    with pytest.raises(TypeError, match="index file root"):
        Indexer.load(str(path))


def test_tokenise_text_handles_apostrophe_words():
    assert list(Indexer.tokenise_text("it's a test")) == ["it's", "a", "test"]


def test_save_and_load_roundtrip(tmp_path: Path, pages_by_url: dict[str, str]):
    indexer = Indexer()
    indexer.build(pages_by_url)

    path = tmp_path / "index.json"
    indexer.save(str(path))

    loaded = Indexer.load(str(path))

    # Verify a few representative postings survived the round-trip.
    assert loaded.doc_lengths == indexer.doc_lengths
    assert (
        loaded.get("twain")["https://quotes.toscrape.com/"].to_dict()
        == indexer.get("twain")["https://quotes.toscrape.com/"].to_dict()
    )
    assert (
        loaded.get("about")["https://quotes.toscrape.com/about"].count
        == indexer.get("about")["https://quotes.toscrape.com/about"].count
    )
