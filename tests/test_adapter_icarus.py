"""Tests for silica.adapters.icarus."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import icarus

FAKE_BIN = "/usr/bin/iverilog"

ICARUS_ERROR = "dut.sv:5: error: Syntax error\n"
ICARUS_WARNING = "dut.sv:3: warning: implicit wire\n"


@patch("silica.adapters.icarus.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = icarus.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("iverilog" in e["message"].lower() or "vvp" in e["message"].lower()
               for e in result["errors"])


@patch("silica.adapters.icarus.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.icarus.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.icarus.subprocess.run")
def test_success(mock_run, mock_which, mock_env):
    mock_run.side_effect = [
        make_proc(returncode=0),
        make_proc(stdout="ok", returncode=0),
    ]
    result = icarus.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert result["trace_vcd"] is None


@patch("silica.adapters.icarus.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.icarus.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.icarus.subprocess.run")
def test_compile_error(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(stderr=ICARUS_ERROR, returncode=1)
    result = icarus.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.icarus.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.icarus.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.icarus.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
def test_timeout_returns_error(mock_run, mock_which, mock_env):
    result = icarus.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_output_error():
    errors, warnings = icarus._parse_output(ICARUS_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


def test_parse_output_warning():
    errors, warnings = icarus._parse_output(ICARUS_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


def test_parse_output_extracts_line_number():
    errors, _ = icarus._parse_output("dut.sv:42: error: some message\n")
    assert errors[0]["line"] == 42
    assert errors[0]["file"] == "dut.sv"


@patch("silica.adapters.icarus.tempfile.mkdtemp")
@patch("silica.adapters.icarus.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.icarus.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.icarus.subprocess.run")
def test_failed_traced_compile_leaves_no_trace_dir(mock_run, mock_which, mock_env, mock_mkdtemp):
    mock_run.return_value = make_proc(stderr=ICARUS_ERROR, returncode=1)
    result = icarus.run("dut.sv", "tb.sv", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)


@patch("silica.adapters.icarus.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.icarus.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.icarus.subprocess.run")
def test_traced_run_uses_dut_dir_and_moves_vcd(mock_run, mock_which, mock_env, tmp_path):
    # Tracing must not change where relative testbench paths ($readmemh) resolve.
    from pathlib import Path

    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()

    def side_effect(cmd, *a, **k):
        if "cwd" in k:  # vvp
            assert k["cwd"] == str(src)
            Path(k["cwd"], "tb.vcd").write_text("$enddefinitions $end\n")
        return make_proc(returncode=0)

    mock_run.side_effect = side_effect
    with patch("silica.adapters.icarus.tempfile.mkdtemp", return_value=str(out)):
        result = icarus.run(str(src / "dut.sv"), str(src / "tb.sv"), trace=True)

    assert result["trace_vcd"] == str(out / "tb.vcd")
    assert not (src / "tb.vcd").exists()
