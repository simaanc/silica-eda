"""Tests for silica.detect (shared tool binary detection)."""

from unittest.mock import patch

from silica.detect import _binaries, resolve


def test_binaries_single_tool():
    assert _binaries("verilator") == ["verilator"]


def test_binaries_list_tool():
    result = _binaries("questa")
    assert "vsim" in result
    assert "qrun" in result


def test_binaries_nextpnr_includes_all_arches():
    result = _binaries("nextpnr")
    for binary in ("nextpnr-ice40", "nextpnr-ecp5", "nextpnr-nexus",
                   "nextpnr-machxo2", "nextpnr-generic", "nextpnr-xilinx"):
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
    with patch("shutil.which",
               side_effect=lambda b: "/usr/bin/nextpnr-ecp5" if b == "nextpnr-ecp5" else None):
        result = resolve("nextpnr")
        assert result == "/usr/bin/nextpnr-ecp5"
