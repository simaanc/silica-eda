"""Tests for silica.adapters.svlint."""

import pytest
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import svlint


# svlint imports shutil inside run(), so mock at the shutil module level
SVLINT_OUTPUT = "dut.sv:5:3: `always_comb` is not implemented [enum_with_type]\n"


@patch("silica.adapters.svlint.resolve", return_value=None)
def test_not_found(mock_which):
    result = svlint.run("dut.sv")
    assert "error" in result
    assert result["warnings"] == []


@patch("silica.adapters.svlint.subprocess.run")
@patch("silica.adapters.svlint.resolve", return_value="/usr/bin/svlint")
def test_success_with_warnings(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=SVLINT_OUTPUT, returncode=1)
    result = svlint.run("dut.sv")
    assert result["tool"] == "svlint"
    assert len(result["warnings"]) >= 1


@patch("silica.adapters.svlint.subprocess.run")
@patch("silica.adapters.svlint.resolve", return_value="/usr/bin/svlint")
def test_clean_file(mock_which, mock_run):
    mock_run.return_value = make_proc(returncode=0)
    result = svlint.run("dut.sv")
    assert result["warnings"] == []


@patch("silica.adapters.svlint.subprocess.run")
@patch("silica.adapters.svlint.resolve", return_value="/usr/bin/svlint")
def test_custom_ruleset(mock_which, mock_run):
    mock_run.return_value = make_proc(returncode=0)
    svlint.run("dut.sv", ruleset="/path/to/rules.toml")
    cmd = mock_run.call_args[0][0]
    assert "--config" in cmd


def test_parse_output():
    warnings = svlint._parse(SVLINT_OUTPUT)
    assert len(warnings) >= 1
    assert all("line" in w for w in warnings)


def test_parse_fail_format():
    text = "Fail: dut.sv: 10:3  enum_with_type\n"
    warnings = svlint._parse(text)
    assert len(warnings) >= 1
    assert warnings[0]["line"] == 10


@patch("silica.adapters.svlint.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=30))
@patch("silica.adapters.svlint.resolve", return_value="/usr/bin/svlint")
def test_timeout_returns_error(mock_resolve, mock_run):
    result = svlint.run("dut.sv")
    assert "timed out" in result["error"]
