"""Tests for silica.adapters.nextpnr."""

from unittest.mock import patch

import pytest
from conftest import make_proc

from silica.adapters import nextpnr

NEXTPNR_OUTPUT = """\
Info: Max frequency for clock 'clk': 72.45 MHz (PASS)
Info: LCs:          100/  7680     1%
Info: FFs:           50/  7680     0%
Warning: Unrouted net: unconnected_wire
"""

NEXTPNR_FAIL_OUTPUT = """\
Info: Max frequency for clock 'clk': 45.00 MHz (FAIL)
ERROR: Failed to place design
"""


# nextpnr-ice40: one report after placement, then the routed result.
NEXTPNR_PLACE_THEN_ROUTE = """\
Info: Max frequency for clock 'clk$SB_IO_IN_$glb_clk': 98.04 MHz (FAIL at 100.00 MHz)
Info: Routing..
Info: Max frequency for clock 'clk$SB_IO_IN_$glb_clk': 146.58 MHz (PASS at 100.00 MHz)
"""


def test_parse_timing_keeps_routed_report_per_clock():
    timing = nextpnr._parse_timing(NEXTPNR_PLACE_THEN_ROUTE)
    assert timing["clocks"] == [
        {"clock": "clk$SB_IO_IN_$glb_clk", "max_freq_mhz": 146.58, "pass": True},
    ]
    assert timing["failing_endpoints"] == 0


@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which, netlist_file):
    result = nextpnr.run(netlist_file)
    assert result["exit_code"] == -1
    assert "nextpnr" in result["errors"][0]["message"].lower()


def test_netlist_not_found():
    result = nextpnr.run("/nonexistent/netlist.json")
    assert result["exit_code"] == -1
    assert "not found" in result["errors"][0]["message"].lower()


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_success_ice40(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout=NEXTPNR_OUTPUT, returncode=0)
    result = nextpnr.run(netlist_file, arch="ice40", device="hx8k")
    assert result["exit_code"] == 0
    assert result["tool"] == "nextpnr-ice40"
    assert len(result["warnings"]) == 1
    assert result["timing_summary"]["clocks"][0]["max_freq_mhz"] == pytest.approx(72.45)
    assert result["timing_summary"]["clocks"][0]["pass"] is True


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ecp5")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_success_ecp5(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout=NEXTPNR_OUTPUT, returncode=0)
    result = nextpnr.run(netlist_file, arch="ecp5", device="LFE5U-45F")
    assert result["exit_code"] == 0
    assert result["tool"] == "nextpnr-ecp5"


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_timing_fail(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout=NEXTPNR_FAIL_OUTPUT, returncode=1)
    result = nextpnr.run(netlist_file)
    assert result["timing_summary"]["clocks"][0]["pass"] is False
    assert len(result["errors"]) > 0


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run",
       side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=120))
def test_timeout(mock_run, mock_which, mock_env, netlist_file):
    result = nextpnr.run(netlist_file)
    assert result["exit_code"] == -1
    assert "timed out" in result["errors"][0]["message"]


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_output_path_resolved(mock_run, mock_which, mock_env, netlist_file, tmp_path):
    mock_run.return_value = make_proc(returncode=0)
    out = "relative_output.asc"
    nextpnr.run(netlist_file, output=out)
    # subprocess should have been called with an absolute path for output
    cmd = mock_run.call_args[0][0]
    asc_args = [a for a in cmd if "relative_output" in a]
    # the path passed should be absolute (resolved)
    from pathlib import Path
    if asc_args:
        assert Path(asc_args[0]).is_absolute()


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_cwd_is_workdir(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(returncode=0)
    nextpnr.run(netlist_file)
    call_kwargs = mock_run.call_args[1]
    assert "cwd" in call_kwargs
    assert call_kwargs["cwd"] is not None


def test_parse_timing_pass():
    raw = "Info: Max frequency for clock 'clk': 100.0 MHz (PASS)\n"
    timing = nextpnr._parse_timing(raw)
    assert len(timing["clocks"]) == 1
    assert timing["clocks"][0]["clock"] == "clk"
    assert timing["clocks"][0]["max_freq_mhz"] == pytest.approx(100.0)
    assert timing["clocks"][0]["pass"] is True
    assert timing["failing_endpoints"] == 0


def test_parse_timing_fail():
    raw = "Info: Max frequency for clock 'clk': 40.0 MHz (FAIL)\n"
    timing = nextpnr._parse_timing(raw)
    assert timing["clocks"][0]["pass"] is False
    assert timing["failing_endpoints"] == 1


def test_parse_utilization():
    raw = "Info: LCs:          100/  7680     1%\n"
    util = nextpnr._parse_utilization(raw)
    assert "LCs" in util
    assert util["LCs"]["used"] == 100
    assert util["LCs"]["total"] == 7680


@pytest.mark.parametrize("arch", ["ice40", "ecp5", "nexus", "machxo2", "generic"])
@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_all_arches(mock_run, mock_which, mock_env, arch, netlist_file):
    mock_run.return_value = make_proc(returncode=0)
    result = nextpnr.run(netlist_file, arch=arch)
    assert result["exit_code"] == 0


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_unparseable_report_flagged(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout="some unrecognized output format", returncode=0)
    result = nextpnr.run(netlist_file)
    assert result["exit_code"] == 0
    assert any("raw_output" in w["message"] for w in result["warnings"])
