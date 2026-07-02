"""Tests for silica.adapters.dc_shell."""

import subprocess
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import dc_shell


FAKE_BIN = "/tools/synopsys/dc_shell"

DC_AREA_OUTPUT = """\
Number of ports:                           10
Number of nets:                            50
Number of cells:                           30
Number of combinational cells:            20
Number of sequential cells:               10
Cell area:                              150.00
"""
DC_ERROR = "Error: (DC-99) Cannot open file 'missing.v'\n"


@patch("silica.adapters.dc_shell.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = dc_shell.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert len(result["errors"]) > 0


@patch("silica.adapters.dc_shell.subprocess.run")
@patch("silica.adapters.dc_shell.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=DC_AREA_OUTPUT, returncode=0)
    result = dc_shell.run("top", ["dut.sv"])
    assert result["exit_code"] == 0
    assert result["tool"] == "dc_shell"
    assert result["utilization"]["luts"] == 20
    assert result["utilization"]["ffs"] == 10


@patch("silica.adapters.dc_shell.subprocess.run")
@patch("silica.adapters.dc_shell.resolve", return_value=FAKE_BIN)
def test_failure(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=DC_ERROR, returncode=1)
    result = dc_shell.run("top", ["dut.sv"])
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.dc_shell.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=300))
@patch("silica.adapters.dc_shell.resolve", return_value=FAKE_BIN)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = dc_shell.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_area_combinational_and_sequential():
    result = dc_shell._parse_area(DC_AREA_OUTPUT)
    assert result["luts"] == 20
    assert result["ffs"] == 10
