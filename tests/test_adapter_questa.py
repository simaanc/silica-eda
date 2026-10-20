"""Tests for silica.adapters.questa."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import questa

FAKE_VSIM = "/tools/questasim/bin/vsim"

QUESTA_ERROR = "** Error: dut.sv(10): Undefined module\n"
QUESTA_WARNING = "** Warning: dut.sv(5): Signal unused\n"


@patch("silica.adapters.questa.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_success(mock_resolve, mock_run):
    # vlib, vlog, vsim
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib work
        make_proc(returncode=0),  # vlog compile
        make_proc(stdout="# Run Complete", returncode=0),  # vsim simulate
    ]
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_compile_error(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib work
        make_proc(stderr=QUESTA_ERROR, returncode=1),  # vlog fails
    ]
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


def test_parse_output_error():
    errors, warnings = questa._parse_output(QUESTA_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"
    assert errors[0]["line"] == 10


def test_parse_output_warning():
    errors, warnings = questa._parse_output(QUESTA_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


def test_parse_output_fatal_is_error():
    text = "** Fatal: (vsimk) User interrupt.\n"
    errors, warnings = questa._parse_output(text)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


@patch("silica.adapters.questa.tempfile.mkdtemp")
@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_failed_traced_compile_leaves_no_trace_dir(mock_resolve, mock_run, mock_mkdtemp):
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib work
        make_proc(stderr=QUESTA_ERROR, returncode=1),  # vlog fails
    ]
    result = questa.run("dut.sv", "tb.sv", trace=True)
    assert result["exit_code"] == 1
    assert not any("trace" in str(kall) for kall in mock_mkdtemp.call_args_list)


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_vlib_failure_reported(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stderr="vlib: cannot create directory", returncode=2)
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 2
    assert any("vlib" in e["message"] for e in result["errors"])
    # vlog/vsim must not run after vlib fails
    assert mock_run.call_count == 1


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_vlib_gets_timeout(mock_resolve, mock_run):
    mock_run.side_effect = [
        make_proc(returncode=0),  # vlib
        make_proc(returncode=0),  # vlog
        make_proc(stdout="run done", returncode=0),  # vsim
    ]
    questa.run("dut.sv", "tb.sv", timeout=17)
    vlib_call = mock_run.call_args_list[0]
    assert vlib_call.kwargs.get("timeout") == 17


@patch("silica.adapters.questa.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = questa.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


# Mocked: these check the working directories and command lines silica
# builds; they don't run Questa.
@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_relative_paths_and_working_dirs(mock_resolve, mock_run, tmp_path, monkeypatch):
    from pathlib import Path

    (tmp_path / "rtl").mkdir()
    (tmp_path / "tb").mkdir()
    monkeypatch.chdir(tmp_path)
    rtl, tb = (tmp_path / "rtl").resolve(), (tmp_path / "tb").resolve()
    mock_run.side_effect = [make_proc(returncode=0)] * 3
    questa.run("rtl/dut.sv", "tb/tb.sv", top="tb", extra_sources=["rtl/sub.sv"])

    vlib, vlog, vsim = mock_run.call_args_list
    tmpdir = vlib.kwargs["cwd"]
    assert vlib.args[0] == ["vlib", "work"]
    # vlog compiles in the temp dir from absolute paths.
    assert vlog.kwargs["cwd"] == tmpdir
    assert vlog.args[0][-3:] == [str(tb / "tb.sv"), str(rtl / "dut.sv"), str(rtl / "sub.sv")]
    # vsim runs in the DUT's directory; library, wlf and transcript stay in the temp dir.
    assert vsim.kwargs["cwd"] == "rtl"
    cmd = vsim.args[0]
    assert cmd[cmd.index("-lib") + 1] == str(Path(tmpdir) / "work")
    assert cmd[cmd.index("-wlf") + 1] == str(Path(tmpdir) / "vsim.wlf")
    assert cmd[cmd.index("-l") + 1] == str(Path(tmpdir) / "transcript")
    assert cmd[-1] == "tb"


@patch("silica.adapters.questa.subprocess.run")
@patch("silica.adapters.questa.resolve", return_value=FAKE_VSIM)
def test_traced_sim_runs_in_dut_dir_with_absolute_vcd(mock_resolve, mock_run, tmp_path,
                                                      monkeypatch):
    (tmp_path / "rtl").mkdir()
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    mock_run.side_effect = [make_proc(returncode=0)] * 3
    with patch("silica.adapters.questa.tempfile.mkdtemp", return_value=str(out)):
        questa.run("rtl/dut.sv", "rtl/tb.sv", trace=True)
    vsim = mock_run.call_args_list[2]
    assert vsim.kwargs["cwd"] == "rtl"
    do_script = vsim.args[0][vsim.args[0].index("-do") + 1]
    assert f"vcd file {out / 'dump.vcd'}" in do_script
