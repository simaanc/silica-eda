"""Tests for silica.adapters.jaspergold."""

import subprocess
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import jaspergold


FAKE_BIN = "/tools/jg/jg"

JG_PASS = "FV Status : Proven\n"
JG_FAIL = "FV Status : Falsified\n"


@patch("silica.adapters.jaspergold.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = jaspergold.run(files=["dut.sv"], top="top")
    assert result["status"] == "ERROR"


@patch("silica.adapters.jaspergold.subprocess.run")
@patch("silica.adapters.jaspergold.resolve", return_value=FAKE_BIN)
def test_pass(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=JG_PASS, returncode=0)
    result = jaspergold.run(files=["dut.sv"], top="top")
    assert result["status"] == "PASS"


@patch("silica.adapters.jaspergold.subprocess.run")
@patch("silica.adapters.jaspergold.resolve", return_value=FAKE_BIN)
def test_fail(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=JG_FAIL, returncode=2)
    result = jaspergold.run(files=["dut.sv"], top="top")
    assert result["status"] == "FAIL"


@patch("silica.adapters.jaspergold.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=300))
@patch("silica.adapters.jaspergold.resolve", return_value=FAKE_BIN)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = jaspergold.run(files=["dut.sv"], top="top")
    assert result["status"] == "ERROR"
    assert any("timed out" in e["message"] for e in result["errors"])


def test_result_has_required_keys():
    with patch("silica.adapters.jaspergold.resolve", return_value=None):
        result = jaspergold.run(files=["dut.sv"], top="top")
        for key in ("status", "rc", "failures", "traces", "warnings", "errors", "workdir", "raw_output"):
            assert key in result


def test_make_tcl_contains_analyze():
    tcl = jaspergold._make_tcl("top", ["dut.sv"], "prove", 20, "clk", "~rst_n")
    assert "top" in tcl
    assert "dut.sv" in tcl


def test_unknown_status_returns_unknown():
    with patch("silica.adapters.jaspergold.resolve", return_value=FAKE_BIN):
        with patch("silica.adapters.jaspergold.subprocess.run") as mock_run:
            mock_run.return_value = make_proc(stdout="no status here", returncode=0)
            result = jaspergold.run(files=["dut.sv"], top="top")
            assert result["status"] == "UNKNOWN"
