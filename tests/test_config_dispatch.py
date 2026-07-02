"""Tests for silica.tools._config_dispatch."""

from unittest.mock import patch

from silica.tools._config_dispatch import pick, is_enabled


def test_pick_uses_fallback_when_no_config():
    with patch("silica.config.load", return_value={}):
        with patch("shutil.which", side_effect=lambda b: "/usr/bin/verilator" if b == "verilator" else None):
            result = pick("simulation")
            assert result == "verilator"


def test_pick_respects_config_priority():
    config = {"tools": {"simulation": {"priority": ["ghdl", "verilator"]}}}
    with patch("silica.config.load", return_value=config):
        with patch("shutil.which", side_effect=lambda b: "/usr/bin/ghdl" if b == "ghdl" else None):
            result = pick("simulation")
            assert result == "ghdl"


def test_pick_returns_none_when_nothing_available():
    with patch("silica.config.load", return_value={}):
        with patch("shutil.which", return_value=None):
            from silica import oss_cad_suite
            with patch.object(oss_cad_suite, "binary_path", return_value=None):
                result = pick("simulation")
                assert result is None


def test_is_enabled_no_config_returns_true():
    with patch("silica.config.load", return_value={}):
        assert is_enabled("simulation", "verilator") is True


def test_is_enabled_present_in_list():
    config = {"tools": {"simulation": {"enabled": ["verilator", "ghdl"]}}}
    with patch("silica.config.load", return_value=config):
        assert is_enabled("simulation", "verilator") is True
        assert is_enabled("simulation", "vcs") is False
