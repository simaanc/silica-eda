"""Tests for silica.adapters._hints."""

from unittest.mock import patch

import pytest

from silica.adapters._hints import _HINTS, install_hint
from silica.tools_registry import TOOLS

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


# _hints.py (curated per-OS prose) and tools_registry.py (per-package-manager
# data) are intentionally separate stores serving different consumers. These
# guards keep them from drifting apart: a new OSS tool added to one but not the
# other would otherwise silently fall back to the generic hint.

def test_every_oss_registry_tool_has_a_hint():
    oss_tools = {n for n, t in TOOLS.items() if t["license"] == "open_source"}
    missing = oss_tools - set(_HINTS)
    assert not missing, f"OSS tools in TOOLS with no _hints.py entry: {sorted(missing)}"


def test_no_orphan_hints():
    orphans = set(_HINTS) - set(TOOLS)
    assert not orphans, f"_hints.py entries with no registry tool: {sorted(orphans)}"
