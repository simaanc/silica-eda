"""Tests for silica.adapters.cocotb_runner and silica.tools.cocotb (run_cocotb)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import MockMCP, make_proc

from silica.adapters import cocotb_runner
from silica.tools import cocotb as cocotb_tool

RESULTS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="cocotb">
    <testcase name="test_pass" time="0.01"/>
    <testcase name="test_fail" time="0.02">
      <failure message="assert failed"/>
    </testcase>
  </testsuite>
</testsuites>
"""


@pytest.fixture
def run_cocotb():
    mcp = MockMCP()
    cocotb_tool.register(mcp)
    return mcp.tools["run_cocotb"]


# --- adapter: pre-flight guards ---

@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=None)
def test_cocotb_not_installed(mock_spec):
    result = cocotb_runner.run(["dut.sv"], "tb.py", "dut")
    assert "error" in result
    assert "cocotb is not installed" in result["error"]


@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=object())
def test_unknown_simulator(mock_spec):
    result = cocotb_runner.run(["dut.sv"], "tb.py", "dut", simulator="bogus")
    assert "error" in result
    assert "Unknown cocotb simulator" in result["error"]


@patch("silica.adapters.cocotb_runner.resolve", return_value=None)
@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=object())
def test_simulator_binary_missing(mock_spec, mock_resolve):
    result = cocotb_runner.run(["dut.sv"], "tb.py", "dut", simulator="icarus")
    assert "error" in result
    assert "iverilog" in result["error"]


@patch("silica.adapters.cocotb_runner.resolve", return_value="/usr/bin/iverilog")
@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=object())
def test_test_module_missing(mock_spec, mock_resolve, tmp_path):
    result = cocotb_runner.run(["dut.sv"], str(tmp_path / "nope.py"), "dut")
    assert "error" in result
    assert "test module not found" in result["error"]


# --- adapter: full run with mocked subprocess writing results.xml ---

@patch("silica.adapters.cocotb_runner.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.cocotb_runner.resolve", return_value="/usr/bin/iverilog")
@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=object())
@patch("silica.adapters.cocotb_runner.subprocess.run")
def test_run_parses_results(mock_run, mock_spec, mock_resolve, mock_env, tmp_path):
    tb = tmp_path / "tb.py"
    tb.write_text("# cocotb test\n")

    def side_effect(cmd, *a, **k):
        # cmd: [python, driver, sim, toplevel, module, build_dir, *sources]
        build_dir = Path(cmd[5])
        (build_dir / "results.xml").write_text(RESULTS_XML)
        return make_proc(returncode=0)

    mock_run.side_effect = side_effect
    result = cocotb_runner.run([str(tmp_path / "dut.sv")], str(tb), "dut")
    assert result["passed"] == 1
    assert result["failed"] == 1
    names = {t["name"]: t["status"] for t in result["tests"]}
    assert names == {"test_pass": "passed", "test_fail": "failed"}


@patch("silica.adapters.cocotb_runner.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.cocotb_runner.resolve", return_value="/usr/bin/iverilog")
@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=object())
@patch("silica.adapters.cocotb_runner.subprocess.run")
def test_build_failure_surfaced(mock_run, mock_spec, mock_resolve, mock_env, tmp_path):
    tb = tmp_path / "tb.py"
    tb.write_text("# cocotb test\n")
    # no results.xml written + nonzero exit == build failed before tests ran
    mock_run.return_value = make_proc(stderr="elaboration error", returncode=2)
    result = cocotb_runner.run([str(tmp_path / "dut.sv")], str(tb), "dut")
    assert "error" in result
    assert "before any test executed" in result["error"]


# --- tool layer ---

@patch("silica.adapters.cocotb_runner.importlib.util.find_spec", return_value=None)
def test_tool_expands_filelist(mock_spec, run_cocotb, tmp_path):
    (tmp_path / "a.sv").write_text("module a; endmodule\n")
    fl = tmp_path / "d.f"
    fl.write_text("a.sv\n")
    # find_spec None short-circuits in the adapter, but expansion happens first
    # in the tool; just assert we reach the adapter cleanly (error passthrough).
    result = run_cocotb([str(fl)], "tb.py", "a")
    assert "error" in result


def test_tool_empty_sources(run_cocotb):
    result = run_cocotb([], "tb.py", "top")
    assert "error" in result
    assert "No source files" in result["error"]


def test_tool_disabled_simulator_rejected(run_cocotb):
    config = {"tools": {"simulation": {"enabled": ["verilator"]}}}
    with patch("silica.config.load", return_value=config):
        result = run_cocotb(["dut.sv"], "tb.py", "dut", simulator="icarus")
    assert "error" in result
    assert "disabled by config" in result["error"]


# --- results parser ---

def test_parse_results_error_element(tmp_path):
    (tmp_path / "results.xml").write_text(
        '<testsuites><testsuite><testcase name="t">'
        '<error message="boom"/></testcase></testsuite></testsuites>'
    )
    tests = cocotb_runner._parse_results(tmp_path)
    assert tests == [{"name": "t", "status": "failed", "time": 0.0, "message": "boom"}]


def test_parse_results_no_xml_is_empty(tmp_path):
    assert cocotb_runner._parse_results(tmp_path) == []
