"""Tests for silica.adapters.vcs."""

import subprocess
import pytest
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import vcs


FAKE_BIN = "/tools/synopsys/vcs"

VCS_ERROR = "Error: dut.sv:10: Undefined module\n"
VCS_WARNING = "Warning: dut.sv:5: Implicit net\n"


@patch("silica.adapters.vcs.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),
        make_proc(stdout="sim ok", returncode=0),
    ]
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert result["trace_vcd"] is None


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_compile_error(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stderr=VCS_ERROR, returncode=1)
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_sim_failure_generic_error(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),
        make_proc(returncode=1),
    ]
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.vcs.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_timeout_propagates(mock_resolve, mock_run):
    with pytest.raises(subprocess.TimeoutExpired):
        vcs.run("dut.sv", "tb.sv")


def test_parse_output_error():
    errors, warnings = vcs._parse_output(VCS_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


def test_parse_output_warning():
    errors, warnings = vcs._parse_output(VCS_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


def test_parse_output_error_with_bracket_code():
    text = "Error-[SE]: Syntax error near 'module'\n"
    errors, warnings = vcs._parse_output(text)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"
