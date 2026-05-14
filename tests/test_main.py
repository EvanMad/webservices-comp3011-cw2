from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.crawler import BASE_URL, POLITENESS_WINDOW
from src.indexer import Indexer
from src.main import (
    build_index,
    load_index,
    main,
    parse_startup_args,
    run_shell,
)


def test_parse_startup_args_defaults():
    ns = parse_startup_args([])
    assert ns.verbose == 0
    assert ns.quiet == 0
    assert ns.start_url == BASE_URL
    assert ns.politeness_window == POLITENESS_WINDOW
    assert str(ns.index_path).endswith("data/index.json")


def test_parse_startup_args_flags_and_overrides():
    ns = parse_startup_args(
        [
            "-vv",
            "-q",
            "--index-path",
            "/tmp/idx.json",
            "--start-url",
            "https://quotes.toscrape.com/tag/love/",
            "--politeness-window",
            "1.5",
        ]
    )
    assert ns.verbose == 2
    assert ns.quiet == 1
    assert ns.index_path == "/tmp/idx.json"
    assert ns.start_url == "https://quotes.toscrape.com/tag/love/"
    assert ns.politeness_window == 1.5


def test_build_index_uses_crawler_and_saves(tmp_path, monkeypatch):
    pages = {
        "https://quotes.toscrape.com/": "<html><body>alpha beta</body></html>",
    }

    class FakeCrawler:
        def __init__(self, base_url=BASE_URL, politeness_window=POLITENESS_WINDOW):
            self.base_url = base_url
            self.politeness_window = politeness_window

        def crawl(self, start_url: str):
            assert start_url == "https://quotes.toscrape.com/start"
            return pages

    monkeypatch.setattr("src.main.Crawler", FakeCrawler)

    out = tmp_path / "nested" / "index.json"
    indexer = build_index(
        start_url="https://quotes.toscrape.com/start",
        index_path=out,
        politeness_window=0,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "index" in loaded
    assert "alpha" in loaded["index"]
    assert indexer.get("alpha")


def test_load_index_roundtrip(tmp_path):
    idx = Indexer()
    idx.add_page("https://example.com/", "<html><body>gamma</body></html>")
    path = tmp_path / "idx.json"
    idx.save(str(path))

    loaded = load_index(index_path=path)
    assert loaded.get("gamma")


def test_run_shell_eof_exits_cleanly(tmp_path, monkeypatch, capsys):
    def eof_input(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof_input)
    code = run_shell(index_path=tmp_path / "missing.json")
    assert code == 0
    assert capsys.readouterr().out == "\n"


def test_run_shell_quit_exits(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "quit")
    assert run_shell(index_path=tmp_path / "i.json") == 0


def test_run_shell_blank_line_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=["", "   ", "quit"]),
    )
    assert run_shell(index_path=tmp_path / "i.json") == 0


def test_main_parses_args_configures_logging_and_runs_shell(tmp_path, monkeypatch):
    idx = tmp_path / "idx.json"
    ns = SimpleNamespace(
        verbose=1,
        quiet=0,
        index_path=str(idx),
        start_url=BASE_URL,
        politeness_window=3.0,
    )
    captured: dict = {}

    def fake_parse(argv: list[str]):
        captured["argv"] = argv
        return ns

    def fake_configure(*, verbose: int, quiet: int):
        captured["log"] = {"verbose": verbose, "quiet": quiet}

    def fake_run_shell(**kwargs):
        captured["shell"] = kwargs
        return 7

    monkeypatch.setattr("src.main.parse_startup_args", fake_parse)
    monkeypatch.setattr("src.main.configure_logging", fake_configure)
    monkeypatch.setattr("src.main.run_shell", fake_run_shell)

    assert main(["-v"]) == 7
    assert captured["argv"] == ["-v"]
    assert captured["log"] == {"verbose": 1, "quiet": 0}
    assert captured["shell"] == {
        "index_path": idx,
        "start_url": BASE_URL,
        "politeness_window": 3.0,
    }


def test_run_shell_unknown_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["nope", "quit"]))
    assert run_shell(index_path=tmp_path / "i.json") == 0
    err = capsys.readouterr().err
    assert "Unknown command" in err


def test_run_shell_shlex_error_then_continue(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=['bad " quote', "quit"]),
    )
    assert run_shell(index_path=tmp_path / "i.json") == 0
    assert "quotation" in capsys.readouterr().err.lower()


def test_run_shell_load_missing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["load", "quit"]))
    assert run_shell(index_path=tmp_path / "none.json") == 0
    assert "No index file" in capsys.readouterr().err


def test_run_shell_load_invalid_json(tmp_path, monkeypatch, capsys):
    path = tmp_path / "bad.json"
    path.write_text("[1,2,3]", encoding="utf-8")
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["load", "quit"]))
    assert run_shell(index_path=path) == 0
    assert "Failed to load index" in capsys.readouterr().err


def test_run_shell_print_requires_loaded_index(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["print foo", "quit"]))
    assert run_shell(index_path=tmp_path / "i.json") == 0
    assert "No index in memory" in capsys.readouterr().err


def test_run_shell_print_wrong_arg_count(tmp_path, monkeypatch, capsys):
    idx_path = tmp_path / "idx.json"
    Indexer().save(str(idx_path))

    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=["load", "print", "print a b", "quit"]),
    )
    assert run_shell(index_path=idx_path) == 0
    err = capsys.readouterr().err
    assert "Usage: print <word>" in err


def test_run_shell_print_ok(tmp_path, monkeypatch, capsys):
    idx = Indexer()
    idx.add_page("https://example.com/", "<html><body>hello</body></html>")
    idx_path = tmp_path / "idx.json"
    idx.save(str(idx_path))

    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=["load", "print hello", "quit"]),
    )
    assert run_shell(index_path=idx_path) == 0
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert "https://example.com/" in parsed


def test_run_shell_find_requires_index(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=["find hello", "quit"]),
    )
    assert run_shell(index_path=tmp_path / "i.json") == 0
    assert "No index in memory" in capsys.readouterr().err


def test_run_shell_find_ok(tmp_path, monkeypatch, capsys):
    idx = Indexer()
    idx.add_page("https://a/", "<html><body>one two</body></html>")
    idx.add_page("https://b/", "<html><body>one three</body></html>")
    idx_path = tmp_path / "idx.json"
    idx.save(str(idx_path))

    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=["load", "find one two", "quit"]),
    )
    assert run_shell(index_path=idx_path) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("http")]
    assert lines == ["https://a/"]


def test_run_shell_build_delegates(monkeypatch, tmp_path):
    called: dict = {}

    def fake_build_index(**kwargs):
        called.update(kwargs)
        indexer = Indexer()
        indexer.add_page("https://x/", "<p>z</p>")
        return indexer

    monkeypatch.setattr("src.main.build_index", fake_build_index)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["build", "quit"]))

    idx_path = tmp_path / "idx.json"
    assert run_shell(index_path=idx_path, politeness_window=2.5) == 0

    assert called["index_path"] == idx_path
    assert called["politeness_window"] == 2.5
