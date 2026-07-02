"""Tests for silica.adapters.spyglass."""

import subprocess
import pytest
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import spyglass


FAKE_BIN = "/tools/synopsys/sg_shell"

# Format: filename.sv line N Violation <RULE_ID> message
SPYGLASS_OUTPUT = "dut.sv line 5 Violation <STARC0513> Multiple assignment to wire\ndut.sv line 10 Violation <STARC0514> Async reset\n"


@patch("silica.adapters.spyglass.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = spyglass.run("dut.sv")
    assert "error" in result
    assert result["warnings"] == []


@patch("silica.adapters.spyglass.subprocess.run")
@patch("silica.adapters.spyglass.resolve", return_value=FAKE_BIN)
def test_success_with_violations(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=SPYGLASS_OUTPUT, returncode=0)
    result = spyglass.run("dut.sv")
    assert result["tool"] == "spyglass"
    assert len(result["warnings"]) >= 1


@patch("silica.adapters.spyglass.subprocess.run")
@patch("silica.adapters.spyglass.resolve", return_value=FAKE_BIN)
def test_clean_file(mock_resolve, mock_run):
    mock_run.return_value = make_proc(returncode=0)
    result = spyglass.run("dut.sv")
    assert result["warnings"] == []
    assert "error" not in result


@patch("silica.adapters.spyglass.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=120))
@patch("silica.adapters.spyglass.resolve", return_value=FAKE_BIN)
def test_timeout_propagates(mock_resolve, mock_run):
    with pytest.raises(subprocess.TimeoutExpired):
        spyglass.run("dut.sv")


def test_parse_violations():
    violations = spyglass._parse_violations(SPYGLASS_OUTPUT, "dut.sv")
    assert len(violations) >= 1
    assert violations[0]["line"] == 5
    assert violations[0]["rule_id"] == "STARC0513"
