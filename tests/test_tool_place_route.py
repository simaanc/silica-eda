"""Tests for silica.tools.place_route (run_place_route MCP tool)."""

import pytest
from unittest.mock import patch
from conftest import MockMCP

from silica.tools import place_route


PNR_SUCCESS = {
    "tool": "nextpnr-ice40", "target": "hx8k", "exit_code": 0,
    "timing_summary": {"clocks": [], "wns": 0.0, "failing_endpoints": 0},
    "utilization": {}, "output": "/tmp/out.asc", "workdir": "/tmp/work",
    "warnings": [], "errors": [], "raw_output": "",
}
PNR_ERROR = {
    "tool": "nextpnr-ice40", "target": "hx8k", "exit_code": -1,
    "timing_summary": {"clocks": [], "wns": 0.0, "failing_endpoints": 0},
    "utilization": {}, "output": None, "workdir": "",
    "warnings": [], "errors": [{"message": "not found"}], "raw_output": "",
}


@pytest.fixture
def run_place_route():
    mcp = MockMCP()
    place_route.register(mcp)
    return mcp.tools["run_place_route"]


@patch("silica.adapters.nextpnr.run", return_value=PNR_SUCCESS)
@patch("silica.tools.place_route.pick", return_value="nextpnr")
def test_auto_picks_nextpnr(mock_pick, mock_run, run_place_route, netlist_file):
    result = run_place_route(netlist_file, tool="auto")
    assert result["exit_code"] == 0
    mock_run.assert_called_once()


@patch("silica.adapters.nextpnr.run", return_value=PNR_SUCCESS)
def test_nextpnr_named(mock_run, run_place_route, netlist_file):
    result = run_place_route(netlist_file, tool="nextpnr")
    assert result["exit_code"] == 0


@patch("silica.adapters.nextpnr.run", return_value=PNR_SUCCESS)
def test_passes_arch_and_device(mock_run, run_place_route, netlist_file):
    run_place_route(netlist_file, arch="ecp5", device="LFE5U-45F", tool="nextpnr")
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs.get("arch") == "ecp5" or mock_run.call_args[0][1] == "ecp5"


def test_unknown_tool_returns_error(run_place_route, netlist_file):
    result = run_place_route(netlist_file, tool="bogus")
    assert result["exit_code"] == -1


@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value=None)
@patch("silica.tools.place_route.pick", return_value=None)
def test_auto_no_tool_returns_error(mock_pick, mock_which, run_place_route, netlist_file):
    result = run_place_route(netlist_file, tool="auto")
    assert result["exit_code"] == -1


@patch("silica.adapters.nextpnr.run", return_value=PNR_ERROR)
def test_not_found_propagated(mock_run, run_place_route, netlist_file):
    result = run_place_route(netlist_file, tool="nextpnr")
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0
