"""Integration tests for the nextpnr adapter (place-and-route)."""

import os

import pytest

from silica import oss_cad_suite
from silica.adapters import nextpnr

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("nextpnr-ice40") is None or oss_cad_suite.which("yosys") is None,
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


_needs = pytest.mark.skipif


@_needs(oss_cad_suite.which("icepack") is None, reason="icepack not installed")
def test_ice40_packs_bitstream(ice40_netlist):
    result = nextpnr.run(netlist=ice40_netlist, arch="ice40", device="hx8k",
                         package="ct256")
    assert result["exit_code"] == 0, result["errors"]
    assert result["output"].endswith(".bin")
    with open(result["output"], "rb") as f:
        # iCE40 bitstreams start with the 0x7EAA997E sync word after a preamble.
        assert b"\x7e\xaa\x99\x7e" in f.read(16)
    assert os.path.exists(os.path.join(result["workdir"], "out.asc"))


@_needs(oss_cad_suite.which("nextpnr-ecp5") is None or oss_cad_suite.which("ecppack") is None,
        reason="nextpnr-ecp5 or ecppack not installed")
def test_ecp5_place_route_and_pack(ecp5_netlist):
    result = nextpnr.run(netlist=ecp5_netlist, arch="ecp5", device="LFE5U-25F-6",
                         package="CABGA381")
    assert result["exit_code"] == 0, result["errors"]
    assert result["tool"] == "nextpnr-ecp5"
    assert result["utilization"]
    assert result["output"].endswith(".bit")
    with open(result["output"], "rb") as f:
        # ecppack writes a comment header naming the part before the bitstream.
        assert b"LFE5U-25F-6CABGA381" in f.read(64)
