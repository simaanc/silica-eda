"""Tests for silica.adapters.vivado."""

import subprocess
import pytest
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import vivado


FAKE_BIN = "/tools/xilinx/vivado"

VIVADO_UTIL = """\
| Slice LUTs*              |   42 |     0 |    17600 |  0.24 |
| Slice Registers          |   20 |     0 |    35200 |  0.06 |
| Block RAM Tile           |    0 |     0 |       60 |  0.00 |
| DSPs                     |    0 |     0 |       80 |  0.00 |
"""

VIVADO_TIMING = """\
WNS(ns)  TNS(ns)  TNS Failing Endpoints
-------  -------  ---------------------
  0.123    0.000  0
"""

VIVADO_ERROR = "ERROR: [Synth 8-285] could not resolve module 'undefined_mod'\n"


@patch("silica.adapters.vivado.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = vivado.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0


@patch("silica.adapters.vivado.subprocess.run")
@patch("silica.adapters.vivado.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=VIVADO_UTIL + VIVADO_TIMING, returncode=0)
    result = vivado.run("top", ["dut.sv"])
    assert result["exit_code"] == 0
    assert result["tool"] == "vivado"
    assert result["utilization"]["luts"] == 42


@patch("silica.adapters.vivado.subprocess.run")
@patch("silica.adapters.vivado.resolve", return_value=FAKE_BIN)
def test_failure(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=VIVADO_ERROR, returncode=1)
    result = vivado.run("top", ["dut.sv"])
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.vivado.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=300))
@patch("silica.adapters.vivado.resolve", return_value=FAKE_BIN)
def test_timeout_propagates(mock_resolve, mock_run):
    with pytest.raises(subprocess.TimeoutExpired):
        vivado.run("top", ["dut.sv"])


def test_parse_utilization():
    util = vivado._parse_utilization(VIVADO_UTIL)
    assert util["luts"] == 42
    assert util["ffs"] == 20


def test_parse_timing_wns():
    timing = vivado._parse_timing(VIVADO_TIMING)
    assert timing["wns"] == pytest.approx(0.123)
    assert timing["failing_endpoints"] == 0


def test_parse_timing_missing_returns_zeros():
    timing = vivado._parse_timing("no timing info here")
    assert timing["wns"] == 0.0


def test_make_tcl_contains_synth_design():
    tcl = vivado._make_tcl("top", ["dut.sv"], "xc7a35tcsg324-1")
    assert "synth_design" in tcl
    assert "top" in tcl
