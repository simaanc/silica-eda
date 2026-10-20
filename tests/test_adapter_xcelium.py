"""Tests for silica.adapters.xcelium."""

import subprocess
from unittest.mock import patch

from conftest import make_proc

from silica.adapters import xcelium

FAKE_BIN = "/tools/cadence/xrun"

XCELIUM_ERROR = "xrun: *E,SYNERR (dut.sv,5|10): Syntax error near 'module'\n"
XCELIUM_WARNING = "xrun: *W,IMPNET (dut.sv,3|1): Implicit net declaration\n"


@patch("silica.adapters.xcelium.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert result["trace_vcd"] is None


@patch("silica.adapters.xcelium.subprocess.run")
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_success(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout="xcelium: *Status: All tests passed", returncode=0)
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 0
    assert result["errors"] == []


@patch("silica.adapters.xcelium.subprocess.run")
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_compile_error(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stderr=XCELIUM_ERROR, returncode=1)
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.xcelium.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=60))
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_timeout_returns_error(mock_resolve, mock_run):
    result = xcelium.run("dut.sv", "tb.sv")
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_parse_output_error():
    errors, warnings = xcelium._parse_output(XCELIUM_ERROR)
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"


def test_parse_output_warning():
    errors, warnings = xcelium._parse_output(XCELIUM_WARNING)
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"


# Mocked: these check the working directory and command line silica builds;
# they don't run Xcelium.
@patch("silica.adapters.xcelium.subprocess.run")
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_runs_in_dut_dir_with_absolute_sources(mock_resolve, mock_run, tmp_path, monkeypatch):
    from pathlib import Path

    (tmp_path / "rtl").mkdir()
    (tmp_path / "tb").mkdir()
    monkeypatch.chdir(tmp_path)
    rtl, tb = (tmp_path / "rtl").resolve(), (tmp_path / "tb").resolve()
    mock_run.return_value = make_proc(returncode=0)
    xcelium.run("rtl/dut.sv", "tb/tb.sv", top="tb", extra_sources=["rtl/sub.sv"])

    call = mock_run.call_args
    assert call.kwargs["cwd"] == "rtl"
    cmd = call.args[0]
    assert cmd[-3:] == [str(tb / "tb.sv"), str(rtl / "dut.sv"), str(rtl / "sub.sv")]
    # The build directory and log go to a temp dir, not the source tree.
    libdir = Path(cmd[cmd.index("-xmlibdirpath") + 1])
    assert libdir.name.startswith("silica_xcelium_")
    assert cmd[cmd.index("-l") + 1] == str(libdir / "xrun.log")


@patch("silica.adapters.xcelium.subprocess.run")
@patch("silica.adapters.xcelium.resolve", return_value=FAKE_BIN)
def test_traced_run_keeps_dut_dir_and_absolute_vcd(mock_resolve, mock_run, tmp_path,
                                                   monkeypatch):
    (tmp_path / "rtl").mkdir()
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    mock_run.return_value = make_proc(returncode=0)
    with patch("silica.adapters.xcelium.tempfile.mkdtemp", return_value=str(out)):
        xcelium.run("rtl/dut.sv", "rtl/tb.sv", trace=True)
    call = mock_run.call_args
    assert call.kwargs["cwd"] == "rtl"
    probe = call.args[0][call.args[0].index("-input") + 1]
    assert f"database -open -vcd {out / 'dump.vcd'}" in probe
