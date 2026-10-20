"""Tests for silica.adapters.verilator."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import verilator

FAKE_BIN = "/usr/bin/verilator"

VERILATOR_WARNING = "%Warning-UNUSED: dut.sv:3:5: Signal is unused\n"
VERILATOR_ERROR = "%Error-PARSE: dut.sv:5:1: Unexpected token\n"


@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("verilator" in e["message"].lower() for e in result["errors"])


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_success(mock_run, mock_which, mock_env):
    mock_run.side_effect = [
        make_proc(stdout="", stderr="", returncode=0),
        make_proc(stdout="sim output", stderr="", returncode=0),
    ]
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert result["trace_vcd"] is None


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_compile_error(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(stderr=VERILATOR_ERROR, returncode=1)
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_compile_failure_without_diagnostics_reports_error(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(stderr="make: *** [Vtb.mk] Error 2\n", returncode=2)
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 2
    assert len(result["errors"]) == 1
    assert "exit code 2" in result["errors"][0]["message"]


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_lint_warnings_are_not_fatal(mock_run, mock_which, mock_env):
    mock_run.side_effect = [make_proc(returncode=0), make_proc(returncode=0)]
    verilator.run("dut.sv", "tb.sv")
    compile_cmd = mock_run.call_args_list[0].args[0]
    assert "-Wall" in compile_cmd
    assert "-Wno-fatal" in compile_cmd


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_warning_parsed(mock_run, mock_which, mock_env):
    mock_run.side_effect = [
        make_proc(stderr=VERILATOR_WARNING, returncode=0),
        make_proc(returncode=0),
    ]
    result = verilator.run("dut.sv", "tb.sv")
    assert len(result["warnings"]) > 0


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
def test_timeout_returns_error(mock_run, mock_which, mock_env):
    result = verilator.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=None)
def test_lint_only_not_found(mock_which):
    result = verilator.lint_only("dut.sv")
    assert result["exit_code"] == -1


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_lint_only_success(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(returncode=0)
    result = verilator.lint_only("dut.sv")
    assert result["exit_code"] == 0
    assert "trace_vcd" not in result


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_lint_only_passes_extra_files(mock_run, mock_which, mock_env):
    mock_run.return_value = make_proc(returncode=0)
    verilator.lint_only("top.sv", extra_files=["sub.sv"])
    cmd = mock_run.call_args[0][0]
    assert cmd[-2:] == ["top.sv", "sub.sv"]


def test_parse_output_error():
    errors, warnings = verilator._parse_output(VERILATOR_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


# --- coverage ---

@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_coverage_flag_and_dat_captured(mock_run, mock_which, mock_env, tmp_path):
    from pathlib import Path

    calls = {"n": 0}

    def side_effect(cmd, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:  # the simulation run — write where the plusarg says
            prefix = "+verilator+coverage+file+"
            dat = next(a for a in cmd if a.startswith(prefix))[len(prefix):]
            Path(dat).write_text("SP\n")
        return make_proc(returncode=0)

    mock_run.side_effect = side_effect
    with patch("silica.adapters.verilator.tempfile.mkdtemp",
               return_value=str(tmp_path)):
        result = verilator.run("dut.sv", "tb.sv", coverage=True)

    compile_cmd = mock_run.call_args_list[0].args[0]
    assert "--coverage" in compile_cmd
    assert result["coverage_dat"] == str(tmp_path / "coverage.dat")


@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=None)
@patch("silica.adapters.verilator.shutil.which", return_value=None)
def test_coverage_info_tool_missing(mock_sw, mock_ow):
    result = verilator.coverage_info("coverage.dat")
    assert "error" in result
    assert "verilator_coverage" in result["error"]


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which",
       return_value="/usr/bin/verilator_coverage")
@patch("silica.adapters.verilator.subprocess.run")
def test_coverage_info_writes_and_reads_info(mock_run, mock_which, mock_env):
    from pathlib import Path

    def side_effect(cmd, *a, **k):
        out = cmd[cmd.index("--write-info") + 1]
        Path(out).write_text("SF:/x.sv\nDA:1,1\nend_of_record\n")
        return make_proc(returncode=0)

    mock_run.side_effect = side_effect
    result = verilator.coverage_info("coverage.dat")
    assert "info" in result
    assert "SF:/x.sv" in result["info"]


def test_parse_output_warning():
    errors, warnings = verilator._parse_output(VERILATOR_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


@patch("silica.adapters.verilator.tempfile.mkdtemp")
@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_failed_traced_compile_leaves_no_trace_dir(mock_run, mock_which, mock_env, mock_mkdtemp):
    mock_run.return_value = make_proc(stderr=VERILATOR_ERROR, returncode=1)
    result = verilator.run("dut.sv", "tb.sv", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)


@patch("silica.adapters.verilator.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.verilator.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.verilator.subprocess.run")
def test_traced_run_uses_dut_dir_and_moves_vcd(mock_run, mock_which, mock_env, tmp_path):
    from pathlib import Path

    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (src / "old.vcd").write_text("untouched")

    def side_effect(cmd, *a, **k):
        if "cwd" in k:  # the simulation run
            assert k["cwd"] == str(src)
            Path(k["cwd"], "tb.vcd").write_text("$enddefinitions $end\n")
        return make_proc(returncode=0)

    mock_run.side_effect = side_effect
    with patch("silica.adapters.verilator.tempfile.mkdtemp", return_value=str(out)):
        result = verilator.run(str(src / "dut.sv"), str(src / "tb.sv"), trace=True)

    assert result["trace_vcd"] == str(out / "tb.vcd")
    assert not (src / "tb.vcd").exists()
    assert (src / "old.vcd").read_text() == "untouched"
