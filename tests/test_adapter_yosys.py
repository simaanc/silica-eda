"""Tests for silica.adapters.yosys."""

import subprocess
from unittest.mock import patch

import pytest
from conftest import make_proc

from silica.adapters import yosys

STAT_OUTPUT = """\
=== top ===
   Number of wires:                 10
   Number of cells:                  3
     $dff                            2
     $lut                            1
"""

YOSYS_WARNING = "Warning: Wire dut.clk is used but never driven.\n"
YOSYS_ERROR = "ERROR: Module not found: undefined_mod\n"


@patch("silica.adapters.yosys.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert result["tool"] == "yosys"
    assert len(result["errors"]) > 0


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_success(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=STAT_OUTPUT, returncode=0)
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == 0
    assert result["tool"] == "yosys"
    assert result["errors"] == []
    assert result["utilization"]["ffs"] == 2
    assert result["utilization"]["luts"] == 1


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_failure(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=YOSYS_ERROR, returncode=1)
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.yosys.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=120))
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_timeout_returns_error(mock_which, mock_run):
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_count_cells_dff_and_lut():
    util = yosys._count_cells(STAT_OUTPUT)
    assert util["ffs"] == 2
    assert util["luts"] == 1
    assert util["bram"] == 0
    assert util["dsp"] == 0


def test_parse_warnings():
    warnings = yosys._parse_warnings(YOSYS_WARNING)
    assert len(warnings) == 1
    assert "Wire" in warnings[0]["message"] or "wire" in warnings[0]["message"].lower()


@pytest.mark.parametrize("target,expected_cmd", [
    ("generic", "synth"),
    ("ice40", "synth_ice40"),
    ("ecp5", "synth_ecp5"),
    ("xilinx", "synth_xilinx"),
    ("gowin", "synth_gowin"),
])
@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_target_selects_synth_command(mock_which, mock_run, target, expected_cmd):
    mock_run.return_value = make_proc(returncode=0)
    yosys.run("top", ["dut.sv"], target=target)
    call_args = mock_run.call_args[0][0]
    script = call_args[2]
    assert expected_cmd in script
