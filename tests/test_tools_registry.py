"""Tests for silica.tools_registry."""

from silica.tools_registry import CATEGORIES, TOOLS

COMMERCIAL_TOOLS = {"vcs", "questa", "xcelium", "vivado", "quartus", "dc_shell",
                    "jaspergold", "vc_formal", "spyglass", "verdi"}

OSS_REQUIRED_KEYS = {"category", "license", "os_support", "install", "url"}
ALL_REQUIRED_KEYS = {"category", "license", "os_support", "url"}


def test_categories_contains_expected():
    for cat in ("simulation", "synthesis", "place_route", "formal", "lint", "waveform", "program"):
        assert cat in CATEGORIES


def test_every_tool_has_base_required_keys():
    for name, tool in TOOLS.items():
        for key in ALL_REQUIRED_KEYS:
            assert key in tool, f"{name} missing key: {key}"


def test_oss_tools_have_required_keys():
    for name, tool in TOOLS.items():
        if name not in COMMERCIAL_TOOLS:
            for key in OSS_REQUIRED_KEYS:
                assert key in tool, f"OSS tool {name} missing key: {key}"


def test_every_tool_category_is_valid():
    for name, tool in TOOLS.items():
        assert tool["category"] in CATEGORIES, f"{name} has invalid category: {tool['category']}"


def test_oss_tools_no_vendor():
    oss_tools = set(TOOLS.keys()) - COMMERCIAL_TOOLS
    for name in oss_tools:
        assert "vendor" not in TOOLS[name], f"OSS tool {name} should not have vendor"


def test_commercial_tools_have_vendor():
    for name in COMMERCIAL_TOOLS:
        if name in TOOLS:
            assert "vendor" in TOOLS[name], f"Commercial tool {name} missing vendor"


def test_tools_dict_is_not_empty():
    assert len(TOOLS) > 10


def test_known_tools_present():
    for tool in ("verilator", "iverilog", "yosys", "sby", "nextpnr", "ghdl", "eqy", "openfpgaloader"):
        assert tool in TOOLS, f"{tool} not in TOOLS"
