"""Tests for silica.adapters.verilator."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import verilator

FAKE_BIN = "/usr/bin/verilator"

VERILATOR_WARNING = "%Warning-UNUSED: dut.sv:3:5: Signal is unused\n"
VERILATOR_ERROR = "%Error-PARSE: dut.sv:5:1: Unexpected token\n"


@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("verilator" in e["message"].lower() for e in result["errors"])


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_success(mock_run, mock_which, mock_env):
    mock_run.side_effect = [
        make_proc(stdout="", stderr="", returncode=0),
        make_proc(stdout="sim output", stderr="", returncode=0),
    ]
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert result["trace_vcd"] is None


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_compile_error(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(stderr=VERILATOR_ERROR, returncode=1)
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_warning_parsed(mock_run, mock_which, mock_env):
    mock_run.side_effect = [
        make_proc(stderr=VERILATOR_WARNING, returncode=0),
        make_proc(returncode=0),
    ]
    result = verilator.run("dut.sv", "tb.sv")
    assert len(result["warnings"]) > 0


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
def test_timeout_returns_error(mock_run, mock_which, mock_env):
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=None)
def test_lint_only_not_found(mock_which):
    result = verilator.lint_only("dut.sv")
    assert result["exit_code"] == -1


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_lint_only_success(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(returncode=0)
    result = verilator.lint_only("dut.sv")
    assert result["exit_code"] == 0
    assert "trace_vcd" not in result


def test_parse_output_error():
    errors, warnings = verilator._parse_output(VERILATOR_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


def test_parse_output_warning():
    errors, warnings = verilator._parse_output(VERILATOR_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


@patch("silica.adapters.verilator.tempfile.mkdtemp")
@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_failed_traced_compile_leaves_no_trace_dir(mock_run, mock_which, mock_env, mock_mkdtemp):
    mock_run.return_value = make_proc(stderr=VERILATOR_ERROR, returncode=1)
    result = verilator.run("dut.sv", "tb.sv", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)
