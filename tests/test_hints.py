"""Tests for silica.adapters._hints."""

from unittest.mock import patch

import pytest

from silica.adapters._hints import install_hint

KNOWN_TOOLS = [
    "verilator", "iverilog", "yosys", "verible-verilog-lint",
    "sby", "surfer", "gtkwave", "svlint", "nextpnr", "ghdl", "eqy", "openfpgaloader",
]

PLATFORMS = ["Darwin", "Linux", "Windows"]


@pytest.mark.parametrize("tool", KNOWN_TOOLS)
@pytest.mark.parametrize("platform", PLATFORMS)
def test_hint_returns_string(tool, platform):
    with patch("platform.system", return_value=platform):
        result = install_hint(tool)
        assert isinstance(result, str)
        assert len(result) > 0


def test_unknown_tool_returns_something():
    result = install_hint("completelyunknowntool")
    assert isinstance(result, str)
