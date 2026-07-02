"""Tests for silica.adapters.eqy."""

from unittest.mock import patch
from conftest import make_proc

from silica.adapters import eqy


EQY_PASS = "DONE (PASS, rc=0)\n"
EQY_FAIL = "Mismatch in output 'q'\nDONE (FAIL, rc=2)\n"


@patch("silica.adapters.eqy.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = eqy.run(eqy_file="check.eqy")
    assert result["status"] == "ERROR"
    assert result["rc"] == -1


def test_eqy_file_not_found():
    result = eqy.run(eqy_file="/nonexistent/check.eqy")
    assert result["status"] == "ERROR"


@patch("silica.adapters.eqy.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.eqy.oss_cad_suite.which", return_value="/usr/bin/eqy")
@patch("silica.adapters.eqy.subprocess.run")
def test_pass(mock_run, mock_which, mock_env, eqy_file):
    mock_run.return_value = make_proc(stdout=EQY_PASS, returncode=0)
    result = eqy.run(eqy_file=eqy_file)
    assert result["status"] == "PASS"
    assert result["rc"] == 0
    assert result["traces"] == []


@patch("silica.adapters.eqy.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.eqy.oss_cad_suite.which", return_value="/usr/bin/eqy")
@patch("silica.adapters.eqy.subprocess.run")
def test_fail(mock_run, mock_which, mock_env, eqy_file):
    mock_run.return_value = make_proc(stdout=EQY_FAIL, returncode=2)
    result = eqy.run(eqy_file=eqy_file)
    assert result["status"] == "FAIL"
    assert len(result["failures"]) > 0
    assert result["failures"][0]["property"] == "q"


@patch("silica.adapters.eqy.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.eqy.oss_cad_suite.which", return_value="/usr/bin/eqy")
@patch("silica.adapters.eqy.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=300))
def test_timeout_returns_error(mock_run, mock_which, mock_env, eqy_file):
    result = eqy.run(eqy_file=eqy_file)
    assert result["status"] == "ERROR"
    assert "timed out" in result["errors"][0]["message"]


@patch("silica.adapters.eqy.sys.platform", "linux")
@patch("silica.adapters.eqy.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.eqy.oss_cad_suite.which", return_value="/usr/bin/eqy")
@patch("silica.adapters.eqy.subprocess.run")
def test_auto_generate_eqy(mock_run, mock_which, mock_env, tmp_path):
    gold = tmp_path / "gold.sv"
    gate = tmp_path / "gate.sv"
    gold.write_text("module top(); endmodule")
    gate.write_text("module top(); endmodule")
    mock_run.return_value = make_proc(stdout=EQY_PASS, returncode=0)
    result = eqy.run(gold_files=[str(gold)], gate_files=[str(gate)], top="top")
    assert result["status"] == "PASS"


def test_generate_eqy_content():
    content = eqy.generate_eqy(["gold.sv"], ["gate.sv"], "top")
    assert "[gold]" in content
    assert "[gate]" in content
    assert "top" in content
    assert "[strategy sat]" in content
