from __future__ import annotations

import logging

import pytest

from src.logging_utils import configure_logging


@pytest.fixture(autouse=True)
def patch_basic_config(monkeypatch):
    captured: dict = {}

    def fake_basic_config(**kwargs):
        captured.clear()
        captured.update(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)
    return captured


def test_configure_logging_default_is_info(patch_basic_config):
    configure_logging(verbose=0, quiet=0)
    assert patch_basic_config["level"] == logging.INFO


def test_configure_logging_verbose_sets_debug(patch_basic_config):
    configure_logging(verbose=1, quiet=0)
    assert patch_basic_config["level"] == logging.DEBUG


def test_configure_logging_quiet_one_sets_warning(patch_basic_config):
    configure_logging(verbose=0, quiet=1)
    assert patch_basic_config["level"] == logging.WARNING


def test_configure_logging_quiet_two_sets_error(patch_basic_config):
    configure_logging(verbose=0, quiet=2)
    assert patch_basic_config["level"] == logging.ERROR


def test_configure_logging_quiet_overrides_verbose(patch_basic_config):
    configure_logging(verbose=2, quiet=1)
    assert patch_basic_config["level"] == logging.WARNING
