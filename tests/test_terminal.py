"""Tests for silica.terminal (OSC-8 hyperlink support detection)."""

import pytest
from unittest.mock import patch

from silica import terminal


def _tty(monkeypatch, is_tty: bool):
    monkeypatch.setattr(terminal.sys.stdout, "isatty", lambda: is_tty, raising=False)


def test_not_a_tty_never_supports(monkeypatch):
    _tty(monkeypatch, False)
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    assert terminal.supports_hyperlinks() is False


@pytest.mark.parametrize("program", [
    "iTerm.app", "WezTerm", "ghostty", "vscode", "Hyper", "tabby",
])
def test_supporting_term_program(monkeypatch, program):
    _tty(monkeypatch, True)
    monkeypatch.setenv("TERM_PROGRAM", program)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    assert terminal.supports_hyperlinks() is True


def test_256color_truecolor_combination(monkeypatch):
    _tty(monkeypatch, True)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert terminal.supports_hyperlinks() is True


def test_256color_without_colorterm(monkeypatch):
    _tty(monkeypatch, True)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("COLORTERM", raising=False)
    assert terminal.supports_hyperlinks() is False


def test_unknown_terminal(monkeypatch):
    _tty(monkeypatch, True)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.delenv("COLORTERM", raising=False)
    assert terminal.supports_hyperlinks() is False


def test_hyperlink_osc8_when_supported():
    with patch.object(terminal, "supports_hyperlinks", return_value=True):
        out = terminal.hyperlink("docs", "https://example.com")
    assert out == "\033]8;;https://example.com\033\\docs\033]8;;\033\\"


def test_hyperlink_fallback_when_unsupported():
    with patch.object(terminal, "supports_hyperlinks", return_value=False):
        out = terminal.hyperlink("docs", "https://example.com")
    assert out == "docs (https://example.com)"


def test_tool_link_and_docs_link_fallback():
    tool = {"url": "https://example.com", "docs": "https://example.com/docs"}
    with patch.object(terminal, "supports_hyperlinks", return_value=False):
        assert terminal.tool_link("yosys", tool) == "yosys (https://example.com)"
        assert terminal.docs_link(tool) == "↗ docs (https://example.com/docs)"


def test_docs_link_falls_back_to_url_key():
    tool = {"url": "https://example.com"}
    with patch.object(terminal, "supports_hyperlinks", return_value=False):
        assert terminal.docs_link(tool) == "↗ docs (https://example.com)"
