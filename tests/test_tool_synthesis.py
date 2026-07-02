"""Tests for silica.tools.synthesis (synthesize MCP tool)."""

from unittest.mock import patch

import pytest
from conftest import MockMCP

from silica.tools import synthesis

SYNTH_SUCCESS = {
    "tool": "yosys", "target": "generic", "exit_code": 0,
    "utilization": {"luts": 10, "ffs": 5, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
    "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
    "warnings": [], "errors": [], "raw_output": "",
}


@pytest.fixture
def synthesize():
    mcp = MockMCP()
    synthesis.register(mcp)
    return mcp.tools["synthesize"]


@patch("silica.adapters.yosys.run", return_value=SYNTH_SUCCESS)
@patch("silica.tools.synthesis.pick", return_value="yosys")
def test_auto_picks_yosys(mock_pick, mock_run, synthesize):
    result = synthesize("top", ["dut.sv"], tool="auto")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.yosys.run", return_value=SYNTH_SUCCESS)
def test_yosys_named(mock_run, synthesize):
    result = synthesize("top", ["dut.sv"], tool="yosys")
    assert result["exit_code"] == 0


@patch("silica.adapters.vivado.run", return_value={**SYNTH_SUCCESS, "tool": "vivado"})
def test_vivado_named(mock_run, synthesize):
    result = synthesize("top", ["dut.sv"], tool="vivado")
    assert result["exit_code"] == 0


@patch("silica.adapters.quartus.run", return_value={**SYNTH_SUCCESS, "tool": "quartus"})
def test_quartus_named(mock_run, synthesize):
    result = synthesize("top", ["dut.sv"], tool="quartus")
    assert result["exit_code"] == 0


@patch("silica.adapters.dc_shell.run", return_value={**SYNTH_SUCCESS, "tool": "dc_shell"})
def test_dc_shell_named(mock_run, synthesize):
    result = synthesize("top", ["dut.sv"], tool="dc_shell")
    assert result["exit_code"] == 0


def test_unknown_tool_returns_error(synthesize):
    result = synthesize("top", ["dut.sv"], tool="bogus")
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0


@patch("silica.tools.synthesis.pick", return_value=None)
def test_auto_no_tool_returns_error(mock_pick, synthesize):
    result = synthesize("top", ["dut.sv"], tool="auto")
    assert result["exit_code"] == -1


# --- config enabled-list enforcement ---

def test_explicit_disabled_tool_rejected(synthesize):
    config = {"tools": {"synthesis": {"enabled": ["yosys"]}}}
    with patch("silica.config.load", return_value=config):
        result = synthesize("top", ["dut.sv"], tool="vivado")
    assert result["exit_code"] == -1
    assert result["errors"][0]["message"] == (
        '"vivado" is disabled by config for category "synthesis"; '
        'enabled: ["yosys"]'
    )


@patch("silica.adapters.yosys.run", return_value=SYNTH_SUCCESS)
def test_explicit_enabled_tool_allowed(mock_run, synthesize):
    config = {"tools": {"synthesis": {"enabled": ["yosys"]}}}
    with patch("silica.config.load", return_value=config):
        result = synthesize("top", ["dut.sv"], tool="yosys")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.vivado.run", return_value=SYNTH_SUCCESS)
def test_no_enabled_config_is_unrestricted(mock_run, synthesize):
    with patch("silica.config.load", return_value={}):
        result = synthesize("top", ["dut.sv"], tool="vivado")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()
