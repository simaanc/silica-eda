"""Tests for script-metacharacter rejection in generated tool scripts."""

import pytest
from unittest.mock import patch
from conftest import MockMCP

from silica.adapters import (
    dc_shell, eqy, jaspergold, quartus, spyglass, vc_formal, vivado, yosys,
)
from silica.adapters._script_paths import unsafe_script_value
from silica.tools import formal


# --- helper ---

@pytest.mark.parametrize("bad", [
    'a".sv', "a}.sv", "a{.sv", "a;.sv", "a$.sv", "a[.sv", "a].sv", "a\n.sv", "a\r.sv",
])
def test_unsafe_script_value_rejects(bad):
    assert unsafe_script_value([bad]) is not None


@pytest.mark.parametrize("ok", [
    "dut.sv", "C:\\proj\\rtl\\dut.sv", "/home/user/rtl/dut.sv",
    "rtl dir/dut file.sv", "top_module", "~rst_n",
])
def test_unsafe_script_value_accepts(ok):
    assert unsafe_script_value(ok) is None


def test_unsafe_script_value_skips_none():
    assert unsafe_script_value(None, ["a.sv"], "top") is None


# --- adapters that build scripts must reject metacharacter paths
#     before any subprocess is launched ---

INJECTION_PATH = 'evil"; exec rm -rf {} ;".sv'


@patch("silica.adapters.yosys.subprocess.run")
def test_yosys_rejects_injection_path(mock_run):
    result = yosys.run("top", [INJECTION_PATH])
    assert result["exit_code"] == -1
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()


@patch("silica.adapters.vivado.subprocess.run")
def test_vivado_rejects_injection_path(mock_run):
    result = vivado.run("top", ["a}.sv"])
    assert result["exit_code"] == -1
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()


@patch("silica.adapters.quartus.subprocess.run")
def test_quartus_rejects_injection_path(mock_run):
    result = quartus.run("top", ['a".sv'])
    assert result["exit_code"] == -1
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()


@patch("silica.adapters.dc_shell.subprocess.run")
def test_dc_shell_rejects_injection_path(mock_run):
    result = dc_shell.run("top", ["a}.sv"])
    assert result["exit_code"] == -1
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()


@patch("silica.adapters.dc_shell.subprocess.run")
def test_dc_shell_rejects_injection_top(mock_run):
    result = dc_shell.run("top; exec evil", ["a.sv"])
    assert result["exit_code"] == -1
    mock_run.assert_not_called()


@patch("silica.adapters.spyglass.subprocess.run")
def test_spyglass_rejects_injection_path(mock_run):
    result = spyglass.run("a}.sv")
    assert "unsafe" in result["error"].lower()
    mock_run.assert_not_called()


@patch("silica.adapters.jaspergold.subprocess.run")
def test_jaspergold_rejects_injection_path(mock_run):
    result = jaspergold.run(files=["a}.sv"], top="top")
    assert result["status"] == "ERROR"
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()


@patch("silica.adapters.vc_formal.subprocess.run")
def test_vc_formal_rejects_injection_path(mock_run):
    result = vc_formal.run(files=["a}.sv"], top="top")
    assert result["status"] == "ERROR"
    mock_run.assert_not_called()


@patch("silica.adapters.eqy.subprocess.run")
def test_eqy_rejects_injection_path(mock_run):
    result = eqy.run(gold_files=["a\n.sv"], gate_files=["b.sv"], top="top")
    assert result["status"] == "ERROR"
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()


def test_run_formal_rejects_injection_before_generating_sby():
    mcp = MockMCP()
    formal.register(mcp)
    run_formal = mcp.tools["run_formal"]
    with patch("silica.adapters.sby.run") as mock_run:
        result = run_formal(files=["a\n.sv"], top="top", tool="sby")
    assert result["status"] == "ERROR"
    assert any("unsafe" in e["message"].lower() for e in result["errors"])
    mock_run.assert_not_called()
