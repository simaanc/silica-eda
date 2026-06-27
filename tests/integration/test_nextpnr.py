"""Integration tests for the nextpnr adapter (place-and-route)."""

import os
import shutil
import pytest
from silica import oss_cad_suite
from silica.adapters import nextpnr

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("nextpnr-ice40") is None or shutil.which("yosys") is None,
        reason="nextpnr-ice40 or yosys not installed",
    ),
]


def test_ice40_pnr_succeeds(ice40_netlist):
    result = nextpnr.run(netlist=ice40_netlist, arch="ice40", device="hx8k")
    assert result["exit_code"] == 0
    assert result["tool"] == "nextpnr-ice40"
    assert result["errors"] == []


def test_result_has_expected_keys(ice40_netlist):
    result = nextpnr.run(netlist=ice40_netlist, arch="ice40", device="hx8k")
    for key in ("exit_code", "tool", "target", "timing_summary", "utilization",
                "output", "workdir", "warnings", "errors", "raw_output"):
        assert key in result


def test_output_file_is_written(ice40_netlist):
    result = nextpnr.run(netlist=ice40_netlist, arch="ice40", device="hx8k")
    assert result["exit_code"] == 0
    assert result["output"] is not None
    assert os.path.exists(result["output"])


def test_timing_structure(ice40_netlist):
    result = nextpnr.run(netlist=ice40_netlist, arch="ice40", device="hx8k")
    timing = result["timing_summary"]
    assert "clocks" in timing
    assert "wns" in timing
    assert "failing_endpoints" in timing


def test_nonexistent_netlist_returns_error():
    result = nextpnr.run(netlist="/nonexistent/counter.json", arch="ice40", device="hx8k")
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0
