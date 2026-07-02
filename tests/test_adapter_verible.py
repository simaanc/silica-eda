"""Tests for silica.adapters.verible."""

from unittest.mock import patch

from conftest import make_proc

from silica.adapters import verible

VERIBLE_OUTPUT = "dut.sv:5:3: Remove trailing whitespace [whitespace/line-length]\ndut.sv:10:1: Line too long [line-length]\n"


@patch("silica.adapters.verible.resolve", return_value=None)
def test_not_found(mock_which):
    result = verible.run("dut.sv")
    assert "error" in result
    assert result["warnings"] == []


@patch("silica.adapters.verible.subprocess.run")
@patch("silica.adapters.verible.resolve", return_value="/usr/bin/verible-verilog-lint")
def test_success_with_warnings(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=VERIBLE_OUTPUT, returncode=0)
    result = verible.run("dut.sv")
    assert result["tool"] == "verible-verilog-lint"
    assert len(result["warnings"]) == 2


@patch("silica.adapters.verible.subprocess.run")
@patch("silica.adapters.verible.resolve", return_value="/usr/bin/verible-verilog-lint")
def test_clean_file_no_warnings(mock_which, mock_run):
    mock_run.return_value = make_proc(returncode=0)
    result = verible.run("dut.sv")
    assert result["warnings"] == []


@patch("silica.adapters.verible.subprocess.run")
@patch("silica.adapters.verible.resolve", return_value="/usr/bin/verible-verilog-lint")
def test_ruleset_all_flag(mock_which, mock_run):
    mock_run.return_value = make_proc(returncode=0)
    verible.run("dut.sv", ruleset="all")
    cmd = mock_run.call_args[0][0]
    assert "--ruleset=all" in cmd


@patch("silica.adapters.verible.subprocess.run")
@patch("silica.adapters.verible.resolve", return_value="/usr/bin/verible-verilog-lint")
def test_custom_ruleset_flag(mock_which, mock_run):
    mock_run.return_value = make_proc(returncode=0)
    verible.run("dut.sv", ruleset="myrules")
    cmd = mock_run.call_args[0][0]
    assert "--rules=myrules" in cmd


def test_parse_warnings():
    warnings = verible._parse(VERIBLE_OUTPUT, "dut.sv")
    assert len(warnings) == 2
    assert warnings[0]["line"] == 5
    assert warnings[1]["line"] == 10
    assert warnings[0]["rule_id"] == "whitespace/line-length"


@patch("silica.adapters.verible.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=30))
@patch("silica.adapters.verible.resolve", return_value="/usr/bin/verible-verilog-lint")
def test_timeout_returns_error(mock_resolve, mock_run):
    result = verible.run("dut.sv")
    assert "timed out" in result["error"]
