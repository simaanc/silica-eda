"""Tests for silica.adapters.quartus."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import quartus

FAKE_BIN = "/tools/altera/quartus_sh"

QUARTUS_REPORT = """\
Total logic elements : 100 / 32,070 ( < 1 % )
Total registers : 50
Total DSP elements : 2 / 70 ( 3 % )
Total memory bits : 0 / 483,840 ( 0 % )
"""
QUARTUS_MSG = "Error (10170): Verilog HDL Module Declaration error at dut.sv(5)\n"


@patch("silica.adapters.quartus.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = quartus.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0


@patch("silica.adapters.quartus.subprocess.run")
@patch("silica.adapters.quartus.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=QUARTUS_REPORT, returncode=0)
    result = quartus.run("top", ["dut.sv"])
    assert result["exit_code"] == 0
    assert result["tool"] == "quartus"
    assert result["utilization"]["luts"] == 100


@patch("silica.adapters.quartus.subprocess.run")
@patch("silica.adapters.quartus.resolve", return_value=FAKE_BIN)
def test_failure(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stderr=QUARTUS_MSG, returncode=1)
    result = quartus.run("top", ["dut.sv"])
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.quartus.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=300))
@patch("silica.adapters.quartus.resolve", return_value=FAKE_BIN)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = quartus.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_report_luts_and_ffs():
    result = quartus._parse_report(QUARTUS_REPORT)
    assert result["luts"] == 100
    assert result["ffs"] == 50
    assert result["dsp"] == 2


@patch("silica.adapters.quartus.subprocess.run")
@patch("silica.adapters.quartus.resolve", return_value=FAKE_BIN)
def test_unparseable_report_flagged(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout="some unrecognized output format", returncode=0)
    result = quartus.run("top", ["dut.sv"])
    assert result["exit_code"] == 0
    assert any("raw_output" in w["message"] for w in result["warnings"])
