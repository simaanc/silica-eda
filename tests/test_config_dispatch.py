"""Tests for silica.tools._config_dispatch."""

from unittest.mock import patch

from silica.tools._config_dispatch import check_enabled, is_enabled, pick


def test_pick_uses_fallback_when_no_config():
    with patch("silica.config.load", return_value={}):
        with patch("shutil.which",
                   side_effect=lambda b: "/usr/bin/verilator" if b == "verilator" else None):
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
    # is_enabled is now the enforcement predicate behind check_enabled and
    # pick(); with no enabled list configured, everything is allowed.
    with patch("silica.config.load", return_value={}):
        assert is_enabled("simulation", "verilator") is True


def test_is_enabled_present_in_list():
    # With an enabled list configured, only listed tools pass the gate.
    config = {"tools": {"simulation": {"enabled": ["verilator", "ghdl"]}}}
    with patch("silica.config.load", return_value=config):
        assert is_enabled("simulation", "verilator") is True
        assert is_enabled("simulation", "vcs") is False


def test_is_enabled_accepts_adapter_alias():
    # Config lists registry names; adapter-side aliases must also pass.
    config = {"tools": {"simulation": {"enabled": ["iverilog"]}}}
    with patch("silica.config.load", return_value=config):
        assert is_enabled("simulation", "icarus") is True
    config = {"tools": {"lint": {"enabled": ["verible-verilog-lint"]}}}
    with patch("silica.config.load", return_value=config):
        assert is_enabled("lint", "verible") is True


def test_check_enabled_allows_when_no_config():
    with patch("silica.config.load", return_value={}):
        assert check_enabled("simulation", "vcs") is None


def test_check_enabled_allows_listed_tool():
    config = {"tools": {"simulation": {"enabled": ["icarus", "verilator"]}}}
    with patch("silica.config.load", return_value=config):
        assert check_enabled("simulation", "verilator") is None


def test_check_enabled_rejects_with_exact_error_shape():
    config = {"tools": {"simulation": {"enabled": ["icarus", "verilator"]}}}
    with patch("silica.config.load", return_value=config):
        msg = check_enabled("simulation", "vcs")
    assert msg == ('"vcs" is disabled by config for category "simulation"; '
                   'enabled: ["icarus", "verilator"]')


def test_pick_skips_disabled_priority_entries():
    config = {"tools": {"simulation": {"priority": ["vcs", "verilator"],
                                       "enabled": ["verilator"]}}}
    with patch("silica.config.load", return_value=config):
        with patch("shutil.which", side_effect=lambda b: f"/usr/bin/{b}"):
            assert pick("simulation") == "verilator"
