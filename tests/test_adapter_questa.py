"""Tests for silica.adapters.questa."""

import pytest
from unittest.mock import patch, MagicMock
from conftest import make_proc

from silica.adapters import questa


FAKE_VSIM = "/tools/questasim/bin/vsim"

QUESTA_ERROR = "** Error: dut.sv(10): Undefined module\n"
QUESTA_WARNING = "** Warning: dut.sv(5): Signal unused\n"


@patch("silica.adapters.questa.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_success(mock_resolve, mock_run):
    # vlib, vlog, vsim
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib work
        make_proc(returncode=0),  # vlog compile
        make_proc(stdout="# Run Complete", returncode=0),  # vsim simulate
    ]
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_compile_error(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib work
        make_proc(stderr=QUESTA_ERROR, returncode=1),  # vlog fails
    ]
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


def test_parse_output_error():
    errors, warnings = questa._parse_output(QUESTA_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"
    assert errors[0]["line"] == 10


def test_parse_output_warning():
    errors, warnings = questa._parse_output(QUESTA_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


def test_parse_output_fatal_is_error():
    text = "** Fatal: (vsimk) User interrupt.\n"
    errors, warnings = questa._parse_output(text)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


@patch("silica.adapters.questa.tempfile.mkdtemp")
@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_failed_traced_compile_leaves_no_trace_dir(mock_resolve, mock_run, mock_mkdtemp):
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib work
        make_proc(stderr=QUESTA_ERROR, returncode=1),  # vlog fails
    ]
    result = questa.run("dut.sv", "tb.sv", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)
