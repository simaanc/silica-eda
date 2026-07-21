"""Tests for silica.setup.print_config output."""

from unittest.mock import patch

import pytest

from silica import setup


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Point config at a temp file and return its path."""
    import silica.config as cfg
    path = tmp_path / "config.toml"
    monkeypatch.setattr(cfg, "_CONFIG_PATH", path)
    monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path)
    return path


def test_print_config_uses_friendly_display_names(config_file, capsys):
    config_file.write_text(
        '[tools.lint]\nenabled = ["verible-verilog-lint"]\n'
    )
    with patch("silica.detect.resolve", return_value="/usr/bin/verible-verilog-lint"):
        setup.print_config()
    out = capsys.readouterr().out
    # The friendly name is shown; the raw registry key is not.
    assert "verible " in out
    assert "verible-verilog-lint" not in out


def test_print_config_shows_configured_project_root(config_file, capsys):
    config_file.write_text('[project]\nroot = "/work/myproj"\n')
    with patch("silica.oss_cad_suite.find_root", return_value=None):
        setup.print_config()
    out = capsys.readouterr().out
    assert "Project root" in out
    assert "/work/myproj" in out


def test_print_config_default_project_root_note(config_file, capsys):
    config_file.write_text('[tools.lint]\nenabled = []\n')
    with patch("silica.oss_cad_suite.find_root", return_value=None):
        setup.print_config()
    out = capsys.readouterr().out
    assert "Project root" in out
    assert "server working directory" in out
