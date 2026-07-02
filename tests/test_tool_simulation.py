"""Tests for silica.tools.simulation (run_simulation MCP tool)."""

import pytest
from unittest.mock import patch
from conftest import MockMCP

from silica.tools import simulation

SIM_SUCCESS = {
    "exit_code": 0, "errors": [], "warnings": [],
    "raw_stdout": "ok", "raw_stderr": "", "trace_vcd": None,
}
SIM_FAIL = {
    "exit_code": 1,
    "errors": [{"file": "dut.sv", "line": 1, "severity": "error", "message": "fail"}],
    "warnings": [], "raw_stdout": "", "raw_stderr": "fail", "trace_vcd": None,
}


@pytest.fixture
def run_simulation():
    mcp = MockMCP()
    simulation.register(mcp)
    return mcp.tools["run_simulation"]


@patch("silica.adapters.verilator.run", return_value=SIM_SUCCESS)
@patch("silica.tools.simulation.pick", return_value="verilator")
def test_auto_picks_verilator(mock_pick, mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="auto")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.icarus.run", return_value=SIM_SUCCESS)
def test_icarus_named(mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="icarus")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.icarus.run", return_value=SIM_SUCCESS)
def test_iverilog_alias_routes_to_icarus(mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="iverilog")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.ghdl.run", return_value=SIM_SUCCESS)
def test_ghdl_named(mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="ghdl")
    assert result["exit_code"] == 0


@patch("silica.adapters.vcs.run", return_value=SIM_SUCCESS)
def test_vcs_named(mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="vcs")
    assert result["exit_code"] == 0


@patch("silica.adapters.questa.run", return_value=SIM_SUCCESS)
def test_questa_named(mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="questa")
    assert result["exit_code"] == 0


@patch("silica.adapters.xcelium.run", return_value=SIM_SUCCESS)
def test_xcelium_named(mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="xcelium")
    assert result["exit_code"] == 0


def test_unknown_simulator_returns_error(run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="bogus")
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0
    assert "bogus" in result["errors"][0]["message"]


@patch("silica.tools.simulation.pick", return_value=None)
def test_auto_no_simulator_returns_error(mock_pick, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="auto")
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0


@patch("silica.adapters.verilator.run", return_value=SIM_FAIL)
@patch("silica.tools.simulation.pick", return_value="verilator")
def test_auto_propagates_failure(mock_pick, mock_run, run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="auto")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0
