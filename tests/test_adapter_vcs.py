"""Tests for silica.adapters.vcs."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import vcs

FAKE_BIN = "/tools/synopsys/vcs"

VCS_ERROR = "Error: dut.sv:10: Undefined module\n"
VCS_WARNING = "Warning: dut.sv:5: Implicit net\n"


@patch("silica.adapters.vcs.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),
        make_proc(stdout="sim ok", returncode=0),
    ]
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert result["trace_vcd"] is None


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_compile_error(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stderr=VCS_ERROR, returncode=1)
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_sim_failure_generic_error(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),
        make_proc(returncode=1),
    ]
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.vcs.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = vcs.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_output_error():
    errors, warnings = vcs._parse_output(VCS_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


def test_parse_output_warning():
    errors, warnings = vcs._parse_output(VCS_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


def test_parse_output_error_with_bracket_code():
    text = "Error-[SE]: Syntax error near 'module'\n"
    errors, warnings = vcs._parse_output(text)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


@patch("silica.adapters.vcs.tempfile.mkdtemp")
@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_failed_traced_compile_leaves_no_trace_dir(mock_resolve, mock_run, mock_mkdtemp):
    mock_run.return_value = make_proc(stderr=VCS_ERROR, returncode=1)
    result = vcs.run("dut.sv", "tb.sv", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)


# Mocked: these check the working directories and command lines silica
# builds; they don't run VCS.
def _project(tmp_path, monkeypatch):
    (tmp_path / "rtl").mkdir()
    (tmp_path / "tb").mkdir()
    monkeypatch.chdir(tmp_path)
    return (tmp_path / "rtl").resolve(), (tmp_path / "tb").resolve()


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_relative_sources_are_resolved_for_the_temp_dir_compile(mock_resolve, mock_run,
                                                                tmp_path, monkeypatch):
    rtl, tb = _project(tmp_path, monkeypatch)
    mock_run.side_effect = [make_proc(returncode=0), make_proc(returncode=0)]
    vcs.run("rtl/dut.sv", "tb/tb.sv", extra_sources=["rtl/sub.sv"])
    compile_call = mock_run.call_args_list[0]
    assert compile_call.args[0][-3:] == [str(tb / "tb.sv"), str(rtl / "dut.sv"),
                                         str(rtl / "sub.sv")]
    assert compile_call.kwargs["cwd"] != "rtl"  # artifacts stay in the temp dir


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_traced_sim_runs_in_dut_dir_and_moves_vcd(mock_resolve, mock_run, tmp_path,
                                                  monkeypatch):
    # Tracing must not change where relative testbench paths ($readmemh) resolve.
    from pathlib import Path

    rtl, _ = _project(tmp_path, monkeypatch)
    out = tmp_path / "out"
    out.mkdir()

    def side_effect(cmd, **kwargs):
        if cmd[0].endswith("simv"):
            assert kwargs["cwd"] == "rtl"
            assert cmd[1:] == ["+vcs+vc+dumpfile+dump.vcd"]
            Path(kwargs["cwd"], "dump.vcd").write_text("$enddefinitions $end\n")
        return make_proc(returncode=0)

    mock_run.side_effect = side_effect
    with patch("silica.adapters.vcs.tempfile.mkdtemp", return_value=str(out)):
        result = vcs.run("rtl/dut.sv", "tb/tb.sv", trace=True)
    assert result["trace_vcd"] == str(out / "dump.vcd")
    assert not (rtl / "dump.vcd").exists()


@patch("silica.adapters.vcs.subprocess.run")
@patch("silica.adapters.vcs.resolve", return_value=FAKE_BIN)
def test_untraced_sim_also_runs_in_dut_dir(mock_resolve, mock_run, tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    mock_run.side_effect = [make_proc(returncode=0), make_proc(returncode=0)]
    vcs.run("rtl/dut.sv", "tb/tb.sv")
    assert mock_run.call_args_list[1].kwargs["cwd"] == "rtl"
