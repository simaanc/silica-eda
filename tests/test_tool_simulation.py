"""Tests for silica.tools.simulation (run_simulation MCP tool)."""

from unittest.mock import patch

import pytest
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


# --- multi-file / filelist support ---

@patch("silica.adapters.icarus.run", return_value=SIM_SUCCESS)
def test_extra_sources_threaded_to_adapter(mock_run, run_simulation):
    run_simulation("dut.sv", "tb.sv", simulator="icarus",
                   extra_sources=["a.sv", "b.sv"])
    _args, kwargs = mock_run.call_args
    assert _args[0] == "dut.sv"          # dut
    assert kwargs["extra_sources"] == ["a.sv", "b.sv"]


@patch("silica.adapters.icarus.run", return_value=SIM_SUCCESS)
def test_filelist_dut_splits_into_dut_plus_extra(mock_run, run_simulation, tmp_path):
    (tmp_path / "sub.sv").write_text("module sub; endmodule\n")
    (tmp_path / "top.sv").write_text("module top; endmodule\n")
    fl = tmp_path / "design.f"
    fl.write_text("sub.sv\ntop.sv\n")

    run_simulation(str(fl), "tb.sv", simulator="icarus")
    args, kwargs = mock_run.call_args
    assert args[0] == str(tmp_path / "sub.sv")             # first listed = dut
    assert kwargs["extra_sources"] == [str(tmp_path / "top.sv")]


def test_missing_filelist_returns_structured_error(run_simulation, tmp_path):
    result = run_simulation(str(tmp_path / "nope.f"), "tb.sv", simulator="icarus")
    assert result["exit_code"] == -1
    assert "filelist" in result["errors"][0]["message"].lower()


# --- coverage flag ---

@patch("silica.adapters.verilator.run", return_value=SIM_SUCCESS)
def test_coverage_threaded_to_verilator(mock_run, run_simulation):
    run_simulation("dut.sv", "tb.sv", simulator="verilator", coverage=True)
    _args, kwargs = mock_run.call_args
    assert kwargs["coverage"] is True


def test_coverage_rejected_for_non_verilator(run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="icarus", coverage=True)
    assert result["exit_code"] == -1
    assert "verilator" in result["errors"][0]["message"].lower()


@patch("silica.adapters.icarus.run", return_value=SIM_SUCCESS)
@patch("silica.tools.simulation.pick", return_value="iverilog")
def test_coverage_rejected_when_auto_resolves_non_verilator(mock_pick, mock_run,
                                                            run_simulation):
    result = run_simulation("dut.sv", "tb.sv", simulator="auto", coverage=True)
    assert result["exit_code"] == -1
    assert "verilator" in result["errors"][0]["message"].lower()


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


# --- config enabled-list enforcement ---

def test_explicit_disabled_simulator_rejected(run_simulation):
    config = {"tools": {"simulation": {"enabled": ["icarus", "verilator"]}}}
    with patch("silica.config.load", return_value=config):
        result = run_simulation("dut.sv", "tb.sv", simulator="vcs")
    assert result["exit_code"] == -1
    assert result["errors"][0]["message"] == (
        '"vcs" is disabled by config for category "simulation"; '
        'enabled: ["icarus", "verilator"]'
    )


@patch("silica.adapters.verilator.run", return_value=SIM_SUCCESS)
def test_explicit_enabled_simulator_allowed(mock_run, run_simulation):
    config = {"tools": {"simulation": {"enabled": ["verilator"]}}}
    with patch("silica.config.load", return_value=config):
        result = run_simulation("dut.sv", "tb.sv", simulator="verilator")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.vcs.run", return_value=SIM_SUCCESS)
def test_no_enabled_config_is_unrestricted(mock_run, run_simulation):
    with patch("silica.config.load", return_value={}):
        result = run_simulation("dut.sv", "tb.sv", simulator="vcs")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()
