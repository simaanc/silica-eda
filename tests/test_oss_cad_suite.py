"""Tests for silica.oss_cad_suite."""

from unittest.mock import patch

from silica import oss_cad_suite


def test_bundled_contains_expected_tools():
    for tool in ("verilator", "iverilog", "yosys", "sby", "ghdl",
                 "eqy", "nextpnr", "openfpgaloader"):
        assert tool in oss_cad_suite.BUNDLED


def test_bin_dir_none_when_no_root():
    with patch.object(oss_cad_suite, "find_root", return_value=None):
        assert oss_cad_suite.bin_dir() is None


def test_binary_path_returns_none_when_no_bin_dir():
    with patch.object(oss_cad_suite, "bin_dir", return_value=None):
        assert oss_cad_suite.binary_path("yosys") is None


def test_binary_path_finds_exe(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "yosys.exe").write_text("")
    with patch.object(oss_cad_suite, "bin_dir", return_value=bin_dir):
        result = oss_cad_suite.binary_path("yosys")
        assert result is not None
        assert "yosys" in result


def test_which_falls_back_to_binary_path(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    yosys = bin_dir / "yosys"
    yosys.write_text("")
    with patch("shutil.which", return_value=None):
        with patch.object(oss_cad_suite, "bin_dir", return_value=bin_dir):
            result = oss_cad_suite.which("yosys")
            assert result is not None


def test_which_returns_system_binary_first():
    with patch("shutil.which", return_value="/usr/bin/yosys"):
        result = oss_cad_suite.which("yosys")
        assert result == "/usr/bin/yosys"


def test_is_installed_false_when_no_root():
    with patch.object(oss_cad_suite, "find_root", return_value=None):
        assert oss_cad_suite.is_installed() is False


def test_is_installed_true_when_root_found(tmp_path):
    with patch.object(oss_cad_suite, "find_root", return_value=tmp_path):
        assert oss_cad_suite.is_installed() is True


def test_env_with_suite_has_path_key():
    env = oss_cad_suite.env_with_suite()
    assert "PATH" in env


def test_env_with_suite_prepends_bin_dir(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Patch find_root (used directly by env_with_suite) rather than bin_dir
    with patch.object(oss_cad_suite, "find_root", return_value=tmp_path):
        env = oss_cad_suite.env_with_suite(base_env={"PATH": "/usr/bin"})
        assert str(bin_dir) in env["PATH"]
