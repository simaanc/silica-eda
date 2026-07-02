"""Tests for silica.adapters.sby."""

from unittest.mock import patch

from conftest import make_proc

from silica.adapters import sby

SBY_PASS_OUTPUT = "DONE (PASS, rc=0)\n"
SBY_FAIL_OUTPUT = (
    "summary: failed assertion my_prop at dut.sv:42\n"
    "DONE (FAIL, rc=2)\n"
)
SBY_ERROR_OUTPUT = "DONE (ERROR, rc=16)\n"


@patch("silica.adapters.sby.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = sby.run("check.sby")
    assert result["status"] == "ERROR"
    assert result["rc"] == -1


def test_file_not_found():
    result = sby.run("/nonexistent/path/check.sby")
    assert result["status"] == "ERROR"
    assert result["rc"] == -1
    assert "not found" in result["errors"][0]["message"].lower()


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_pass(mock_run, mock_which, mock_env, sby_file):
    mock_run.return_value = make_proc(stdout=SBY_PASS_OUTPUT, returncode=0)
    result = sby.run(sby_file)
    assert result["status"] == "PASS"
    assert result["rc"] == 0
    assert result["failures"] == []


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_fail(mock_run, mock_which, mock_env, sby_file):
    mock_run.return_value = make_proc(stdout=SBY_FAIL_OUTPUT, returncode=2)
    result = sby.run(sby_file)
    assert result["status"] == "FAIL"
    assert len(result["failures"]) == 1
    assert result["failures"][0]["property"] == "my_prop"
    assert result["failures"][0]["file"] == "dut.sv"
    assert result["failures"][0]["line"] == 42


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_error_status(mock_run, mock_which, mock_env, sby_file):
    mock_run.return_value = make_proc(stdout=SBY_ERROR_OUTPUT, returncode=16)
    result = sby.run(sby_file)
    assert result["status"] == "ERROR"


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run",
       side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=300))
def test_timeout(mock_run, mock_which, mock_env, sby_file):
    result = sby.run(sby_file)
    assert result["status"] == "UNKNOWN"
    assert "timed out" in result["errors"][0]["message"]


def test_generate_sby_contains_sections():
    content = sby.generate_sby(["dut.sv"], "top", mode="bmc", depth=10)
    assert "[options]" in content
    assert "mode bmc" in content
    assert "depth 10" in content
    assert "[engines]" in content
    assert "[script]" in content
    assert "[files]" in content
    assert "top" in content


def test_generate_sby_auto_engine_no_solver():
    with patch("silica.adapters.sby.oss_cad_suite.which", return_value=None):
        content = sby.generate_sby(["dut.sv"], "top", engine="auto")
        assert "smtbmc" in content


def test_generate_sby_auto_engine_with_solver():
    with patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/z3"):
        with patch("silica.adapters.sby._detect_solver", return_value="z3"):
            content = sby.generate_sby(["dut.sv"], "top", engine="auto")
            assert "smtbmc" in content


@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/z3")
def test_detect_solver_finds_z3(mock_which):
    solver = sby._detect_solver()
    assert solver == "z3"


@patch("silica.adapters.sby.oss_cad_suite.which", return_value=None)
def test_detect_solver_empty_when_none(mock_which):
    solver = sby._detect_solver()
    assert solver == ""
