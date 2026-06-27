"""Tests for silica.cli."""

import sys
import pytest
from unittest.mock import patch, MagicMock

from silica import cli


def test_main_serve_calls_mcp_run(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["silica", "serve"])
    mock_mcp = MagicMock()
    with patch("silica.server.mcp", mock_mcp):
        cli.main()
    mock_mcp.run.assert_called_once()


def test_main_setup_calls_setup_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["silica", "setup"])
    with patch("silica.setup.main") as mock_setup:
        cli.main()
    mock_setup.assert_called_once()


def test_main_config_calls_print_config(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["silica", "config"])
    with patch("silica.setup.print_config") as mock_print:
        cli.main()
    mock_print.assert_called_once()


def test_main_unknown_command_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["silica", "bogus"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 1


def test_main_no_args_defaults_to_serve(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["silica"])
    mock_mcp = MagicMock()
    with patch("silica.server.mcp", mock_mcp):
        cli.main()
    mock_mcp.run.assert_called_once()
