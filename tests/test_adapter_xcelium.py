"""Tests for silica.adapters.xcelium."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import xcelium

FAKE_BIN = "/tools/cadence/xrun"

XCELIUM_ERROR = "xrun: *E,SYNERR (dut.sv,5|10): Syntax error near 'module'\n"
XCELIUM_WARNING = "xrun: *W,IMPNET (dut.sv,3|1): Implicit net declaration\n"


@patch("silica.adapters.xcelium.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.xcelium.subprocess.run")
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout="xcelium: *Status: All tests passed", returncode=0)
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []


@patch("silica.adapters.xcelium.subprocess.run")
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_compile_error(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stderr=XCELIUM_ERROR, returncode=1)
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.xcelium.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_output_error():
    errors, warnings = xcelium._parse_output(XCELIUM_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


def test_parse_output_warning():
    errors, warnings = xcelium._parse_output(XCELIUM_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"
