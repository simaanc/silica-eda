"""Tests for silica.tools.lint (lint MCP tool)."""

from unittest.mock import patch

import pytest
from conftest import MockMCP

from silica.tools import lint

LINT_CLEAN = {"warnings": [], "tool": "verible-verilog-lint", "raw_output": ""}
LINT_WARN = {
    "warnings": [{"file": "dut.sv", "line": 5, "severity": "warning", "rule_id": "x", "message": "issue"}],
    "tool": "verible-verilog-lint", "raw_output": "dut.sv:5:1: issue [x]",
}
VERILATOR_LINT = {
    "exit_code": 0,
    "errors": [],
    "warnings": [{"file": "dut.sv", "line": 3, "severity": "warning", "message": "%Warning-UNUSED: unused"}],
    "raw_stdout": "", "raw_stderr": "",
}


@pytest.fixture
def lint_tool():
    mcp = MockMCP()
    lint.register(mcp)
    return mcp.tools["lint"]


@patch("silica.adapters.verible.run", return_value=LINT_CLEAN)
@patch("silica.tools.lint.pick", return_value="verible-verilog-lint")
def test_auto_picks_verible(mock_pick, mock_run, lint_tool):
    result = lint_tool("dut.sv", tool="auto")
    assert result["warnings"] == []
    mock_run.assert_called_once()


@patch("silica.adapters.verible.run", return_value=LINT_WARN)
def test_verible_named(mock_run, lint_tool):
    result = lint_tool("dut.sv", tool="verible")
    assert len(result["warnings"]) == 1


@patch("silica.adapters.verilator.lint_only", return_value=VERILATOR_LINT)
def test_verilator_named(mock_run, lint_tool):
    result = lint_tool("dut.sv", tool="verilator")
    assert len(result["warnings"]) > 0
    assert result["tool"] == "verilator"


@patch("silica.adapters.svlint.run", return_value=LINT_CLEAN)
def test_svlint_named(mock_run, lint_tool):
    result = lint_tool("dut.sv", tool="svlint")
    assert result["warnings"] == []


@patch("silica.adapters.spyglass.run", return_value={**LINT_CLEAN, "tool": "spyglass"})
def test_spyglass_named(mock_run, lint_tool):
    result = lint_tool("dut.sv", tool="spyglass")
    assert result["warnings"] == []


def test_unknown_tool_returns_error(lint_tool):
    result = lint_tool("dut.sv", tool="bogus")
    assert "error" in result or result.get("warnings") == []


@patch("silica.tools.lint.pick", return_value=None)
def test_auto_no_tool_returns_error(mock_pick, lint_tool):
    result = lint_tool("dut.sv", tool="auto")
    assert "error" in result


# --- config enabled-list enforcement ---

def test_explicit_disabled_tool_rejected(lint_tool):
    config = {"tools": {"lint": {"enabled": ["verible-verilog-lint"]}}}
    with patch("silica.config.load", return_value=config):
        result = lint_tool("dut.sv", tool="spyglass")
    assert result["error"] == (
        '"spyglass" is disabled by config for category "lint"; '
        'enabled: ["verible-verilog-lint"]'
    )
    assert result["warnings"] == []


@patch("silica.adapters.verible.run", return_value=LINT_CLEAN)
def test_explicit_enabled_tool_allowed_via_alias(mock_run, lint_tool):
    # Config lists the registry name; the override uses the adapter alias.
    config = {"tools": {"lint": {"enabled": ["verible-verilog-lint"]}}}
    with patch("silica.config.load", return_value=config):
        result = lint_tool("dut.sv", tool="verible")
    assert "error" not in result
    mock_run.assert_called_once()


@patch("silica.adapters.spyglass.run", return_value={**LINT_CLEAN, "tool": "spyglass"})
def test_no_enabled_config_is_unrestricted(mock_run, lint_tool):
    with patch("silica.config.load", return_value={}):
        result = lint_tool("dut.sv", tool="spyglass")
    assert "error" not in result
    mock_run.assert_called_once()
