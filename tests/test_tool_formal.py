"""Tests for silica.tools.formal (run_formal MCP tool)."""

import pytest
from unittest.mock import patch
from conftest import MockMCP

from silica.tools import formal


FORMAL_PASS = {
    "status": "PASS", "rc": 0,
    "failures": [], "traces": [], "warnings": [], "errors": [],
    "workdir": "/tmp/work", "raw_output": "DONE (PASS, rc=0)",
}
FORMAL_FAIL = {
    "status": "FAIL", "rc": 2,
    "failures": [{"property": "p", "file": "dut.sv", "line": 1}],
    "traces": [], "warnings": [], "errors": [],
    "workdir": "/tmp/work", "raw_output": "DONE (FAIL, rc=2)",
}
FORMAL_ERROR = {
    "status": "ERROR", "rc": -1,
    "failures": [], "traces": [], "warnings": [],
    "errors": [{"file": "", "line": 0, "message": "not found"}],
    "workdir": "", "raw_output": "",
}


@pytest.fixture
def run_formal():
    mcp = MockMCP()
    formal.register(mcp)
    return mcp.tools["run_formal"]


@patch("silica.adapters.sby.run", return_value=FORMAL_PASS)
def test_sby_with_file(mock_run, run_formal, sby_file):
    result = run_formal(sby_file=sby_file, tool="sby")
    assert result["status"] == "PASS"


@patch("silica.adapters.sby.run", return_value=FORMAL_PASS)
@patch("silica.adapters.sby.generate_sby", return_value="[options]\nmode prove\n")
def test_sby_auto_generate(mock_gen, mock_run, run_formal, sv_file):
    result = run_formal(files=[sv_file], top="top", tool="sby")
    assert result["status"] == "PASS"
    assert "generated_sby" in result


@patch("silica.adapters.sby.run", return_value=FORMAL_PASS)
def test_sby_auto_generate_copies_sources_next_to_config(mock_run, run_formal, tmp_path):
    # generate_sby emits basenames in [files], which sby resolves against the
    # .sby's directory — the sources must be copied into the generated dir.
    from pathlib import Path
    src = tmp_path / "dut.sv"
    src.write_text("module dut(); endmodule\n")
    run_formal(files=[str(src)], top="dut", tool="sby")
    sby_path = Path(mock_run.call_args.args[0])
    assert sby_path.name == "dut.sby"
    assert (sby_path.parent / "dut.sv").exists()
    assert (sby_path.parent / "dut.sv").read_text() == src.read_text()


@patch("silica.adapters.eqy.run", return_value={**FORMAL_PASS, "traces": []})
def test_eqy_with_file(mock_run, run_formal, eqy_file):
    result = run_formal(sby_file=eqy_file, tool="eqy")
    assert result["status"] == "PASS"


@patch("silica.adapters.jaspergold.run", return_value=FORMAL_PASS)
def test_jaspergold_named(mock_run, run_formal, sv_file):
    result = run_formal(files=[sv_file], top="top", tool="jaspergold")
    assert result["status"] == "PASS"


@patch("silica.adapters.vc_formal.run", return_value=FORMAL_PASS)
def test_vc_formal_named(mock_run, run_formal, sv_file):
    result = run_formal(files=[sv_file], top="top", tool="vc_formal")
    assert result["status"] == "PASS"


@patch("silica.adapters.sby.run", return_value=FORMAL_PASS)
@patch("silica.tools.formal.pick", return_value="sby")
def test_auto_picks_sby(mock_pick, mock_run, run_formal, sby_file):
    result = run_formal(sby_file=sby_file, tool="auto")
    assert result["status"] == "PASS"


@patch("silica.tools.formal.pick", return_value=None)
def test_auto_no_tool_returns_error(mock_pick, run_formal):
    result = run_formal(tool="auto")
    assert result["status"] == "ERROR"
    assert result["rc"] == -1


def test_unknown_tool_returns_error(run_formal):
    result = run_formal(tool="bogus")
    assert result["status"] == "ERROR"


@patch("silica.adapters.sby.run", return_value=FORMAL_FAIL)
@patch("silica.adapters.sby.generate_sby", return_value="[options]\nmode prove\n")
def test_generate_sby_fail_propagates(mock_gen, mock_run, run_formal, sv_file):
    result = run_formal(files=[sv_file], top="top", tool="sby")
    assert result["status"] == "FAIL"
    assert len(result["failures"]) > 0


@patch("silica.adapters.eqy.run", return_value=FORMAL_PASS)
def test_eqy_gold_gate_files(mock_run, run_formal, tmp_path):
    gold = tmp_path / "gold.sv"
    gate = tmp_path / "gate.sv"
    gold.write_text("module top(); endmodule")
    gate.write_text("module top(); endmodule")
    result = run_formal(gold_files=[str(gold)], gate_files=[str(gate)], top="top", tool="eqy")
    assert result["status"] == "PASS"
