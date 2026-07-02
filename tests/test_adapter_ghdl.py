"""Tests for silica.adapters.ghdl."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import ghdl

FAKE_BIN = "/usr/bin/ghdl"

GHDL_ERROR = "dut.vhd:5:10: error[SYNTH]: undefined symbol\n"
GHDL_WARNING = "dut.vhd:3:1: warning: signal assigned but not read\n"


@patch("silica.adapters.ghdl.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = ghdl.run("dut.vhd", "tb.vhd")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.ghdl.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.ghdl.subprocess.run")
def test_success(mock_run, mock_which):
    mock_run.side_effect = [
        make_proc(returncode=0),
        make_proc(returncode=0),
        make_proc(stdout="sim output", returncode=0),
    ]
    result = ghdl.run("dut.vhd", "tb.vhd", top="tb")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert result["trace_vcd"] is None


@patch("silica.adapters.ghdl.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.ghdl.subprocess.run")
def test_analyze_error(mock_run, mock_which):
    mock_run.return_value = make_proc(stderr=GHDL_ERROR, returncode=1)
    result = ghdl.run("dut.vhd", "tb.vhd")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.ghdl.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.ghdl.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
def test_timeout_returns_error(mock_run, mock_which):
    result = ghdl.run("dut.vhd", "tb.vhd")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_output_error():
    errors, warnings = ghdl._parse_output(GHDL_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"
    assert errors[0]["line"] == 5
    assert errors[0]["file"] == "dut.vhd"


def test_parse_output_warning():
    errors, warnings = ghdl._parse_output(GHDL_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


@patch("silica.adapters.ghdl.tempfile.mkdtemp")
@patch("silica.adapters.ghdl.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.ghdl.subprocess.run")
def test_failed_traced_analyze_leaves_no_trace_dir(mock_run, mock_which, mock_mkdtemp):
    mock_run.return_value = make_proc(stderr=GHDL_ERROR, returncode=1)
    result = ghdl.run("dut.vhd", "tb.vhd", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)
