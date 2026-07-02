"""Tests for silica.tools._config_dispatch."""

import pytest
from unittest.mock import patch

from silica.tools._config_dispatch import _binaries, resolve, pick, is_enabled


def test_binaries_single_tool():
    assert _binaries("verilator") == ["verilator"]


def test_binaries_list_tool():
    result = _binaries("questa")
    assert "vsim" in result
    assert "qrun" in result


def test_binaries_nextpnr_includes_all_arches():
    result = _binaries("nextpnr")
    for binary in ("nextpnr-ice40", "nextpnr-ecp5", "nextpnr-nexus", "nextpnr-machxo2", "nextpnr-generic"):
        assert binary in result


def test_binaries_unknown_tool_uses_name():
    assert _binaries("somefaketool") == ["somefaketool"]


def test_resolve_finds_on_system_path():
    with patch("shutil.which", return_value="/usr/bin/verilator"):
        result = resolve("verilator")
        assert result == "/usr/bin/verilator"


def test_resolve_falls_back_to_oss_suite():
    from silica import oss_cad_suite
    with patch("shutil.which", return_value=None):
        with patch.object(oss_cad_suite, "binary_path", return_value="/oss/bin/sby"):
            result = resolve("sby")
            assert result == "/oss/bin/sby"


def test_resolve_returns_none_when_not_found():
    from silica import oss_cad_suite
    with patch("shutil.which", return_value=None):
        with patch.object(oss_cad_suite, "binary_path", return_value=None):
            result = resolve("verilator")
            assert result is None


def test_resolve_nextpnr_finds_any_arch():
    with patch("shutil.which", side_effect=lambda b: "/usr/bin/nextpnr-ecp5" if b == "nextpnr-ecp5" else None):
        result = resolve("nextpnr")
        assert result == "/usr/bin/nextpnr-ecp5"


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
