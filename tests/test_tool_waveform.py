"""Tests for silica.tools.waveform (launch_waveform, read_waveform MCP tools)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from conftest import MockMCP

from silica.tools import waveform


@pytest.fixture
def launch_waveform():
    mcp = MockMCP()
    waveform.register(mcp)
    return mcp.tools["launch_waveform"]


@pytest.fixture
def vcd_file(tmp_path):
    f = tmp_path / "sim.vcd"
    f.write_text("$timescale 1ns $end\n")
    return str(f)


@patch("silica.tools.waveform.subprocess.Popen")
@patch("silica.tools.waveform.resolve", return_value="/usr/bin/surfer")
def test_surfer_named(mock_resolve, mock_popen, launch_waveform, vcd_file):
    mock_popen.return_value = MagicMock()
    result = launch_waveform(vcd_file, viewer="surfer")
    assert result["launched"] is True
    assert result["viewer"] == "surfer"


@patch("silica.tools.waveform.subprocess.Popen")
@patch("silica.tools.waveform.resolve", return_value="/usr/bin/gtkwave")
def test_gtkwave_named(mock_resolve, mock_popen, launch_waveform, vcd_file):
    mock_popen.return_value = MagicMock()
    result = launch_waveform(vcd_file, viewer="gtkwave")
    assert result["launched"] is True
    assert result["viewer"] == "gtkwave"


@patch("silica.adapters.verdi.launch",
       return_value={"launched": True, "viewer": "verdi", "trace": "sim.vcd"})
def test_verdi_named(mock_launch, launch_waveform, vcd_file):
    result = launch_waveform(vcd_file, viewer="verdi")
    assert result["launched"] is True
    assert result["viewer"] == "verdi"


@patch("silica.tools.waveform.subprocess.Popen")
@patch("silica.tools.waveform.resolve", return_value="/usr/bin/surfer")
@patch("silica.tools.waveform.pick", return_value="surfer")
def test_auto_picks_surfer(mock_pick, mock_resolve, mock_popen, launch_waveform, vcd_file):
    mock_popen.return_value = MagicMock()
    result = launch_waveform(vcd_file, viewer="auto")
    assert result["launched"] is True
    assert result["viewer"] == "surfer"


@patch("silica.tools.waveform.pick", return_value=None)
def test_auto_no_viewer_fails(mock_pick, launch_waveform, vcd_file):
    result = launch_waveform(vcd_file, viewer="auto")
    assert result["launched"] is False
    assert "error" in result


@patch("silica.tools.waveform.resolve", return_value=None)
@patch("silica.tools.waveform.shutil.which", return_value=None)
def test_named_viewer_not_found_fails(mock_which, mock_resolve, launch_waveform, vcd_file):
    result = launch_waveform(vcd_file, viewer="surfer")
    assert result["launched"] is False


# --- config enabled-list enforcement ---

def test_explicit_disabled_viewer_rejected(launch_waveform):
    config = {"tools": {"waveform": {"enabled": ["surfer"]}}}
    with patch("silica.config.load", return_value=config):
        result = launch_waveform("trace.vcd", viewer="gtkwave")
    assert result["launched"] is False
    assert result["error"] == (
        '"gtkwave" is disabled by config for category "waveform"; '
        'enabled: ["surfer"]'
    )


@patch("silica.tools.waveform.subprocess.Popen")
@patch("silica.tools.waveform.resolve", return_value="/usr/bin/surfer")
def test_explicit_enabled_viewer_allowed(mock_resolve, mock_popen, launch_waveform):
    config = {"tools": {"waveform": {"enabled": ["surfer"]}}}
    with patch("silica.config.load", return_value=config):
        result = launch_waveform("trace.vcd", viewer="surfer")
    assert result["launched"] is True
    mock_popen.assert_called_once()


@patch("silica.tools.waveform.subprocess.Popen")
@patch("silica.tools.waveform.resolve", return_value="/usr/bin/gtkwave")
def test_no_enabled_config_is_unrestricted(mock_resolve, mock_popen, launch_waveform):
    with patch("silica.config.load", return_value={}):
        result = launch_waveform("trace.vcd", viewer="gtkwave")
    assert result["launched"] is True
    mock_popen.assert_called_once()


# --- read_waveform ---

COUNTER_VCD = """\
$timescale 1ns $end
$scope module tb $end
$var reg 1 ! clk $end
$scope module dut $end
$var reg 4 " count [3:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
$dumpvars
0!
bx "
$end
#5
1!
b1 "
#10
0!
#15
1!
b10 "
"""


@pytest.fixture
def read_waveform():
    mcp = MockMCP()
    waveform.register(mcp)
    return mcp.tools["read_waveform"]


@pytest.fixture
def counter_vcd(tmp_path):
    f = tmp_path / "sim.vcd"
    f.write_text(COUNTER_VCD)
    return str(f)


def test_discovery_mode_lists_signals(read_waveform, counter_vcd):
    result = read_waveform(counter_vcd)
    assert result["signal_count"] == 2
    names = [s["name"] for s in result["signals"]]
    assert "tb.dut.count" in names
    assert result["timescale"] == "1ns"
    assert result["end_time"] == 15


def test_reads_requested_signal(read_waveform, counter_vcd):
    result = read_waveform(counter_vcd, signals=["dut.count"])
    assert result["not_found"] == []
    sig = result["signals"][0]
    assert sig["name"] == "tb.dut.count"
    assert {"time": 5, "value": "0001"} in sig["transitions"]
    assert {"time": 15, "value": "0010"} in sig["transitions"]


def test_time_window(read_waveform, counter_vcd):
    result = read_waveform(
        counter_vcd, signals=["dut.count"], time_start=10, time_end=15)
    tr = result["signals"][0]["transitions"]
    assert tr[0] == {"time": 10, "value": "0001"}
    assert tr[-1] == {"time": 15, "value": "0010"}


def test_unknown_signal_gets_hint(read_waveform, counter_vcd):
    result = read_waveform(counter_vcd, signals=["bogus"])
    assert result["not_found"] == ["bogus"]
    assert "hint" in result


def test_missing_file_returns_error(read_waveform):
    result = read_waveform("/nonexistent/sim.vcd")
    assert "error" in result


def test_fsdb_rejected(read_waveform, tmp_path):
    f = tmp_path / "sim.fsdb"
    f.write_bytes(b"\x00\x01")
    result = read_waveform(str(f))
    assert "error" in result
    assert "FSDB" in result["error"]


def test_malformed_vcd_returns_error(read_waveform, tmp_path):
    f = tmp_path / "junk.vcd"
    f.write_text("not a vcd\n")
    result = read_waveform(str(f))
    assert "error" in result


# --- FST support (via fst2vcd) ---

def test_fst_without_converter_errors(read_waveform, tmp_path):
    f = tmp_path / "sim.fst"
    f.write_bytes(b"\x00\x01")
    with patch("silica.tools.waveform.oss_cad_suite.which", return_value=None):
        result = read_waveform(str(f))
    assert "error" in result
    assert "fst2vcd" in result["error"]


def test_fst_converted_then_parsed(read_waveform, tmp_path):
    f = tmp_path / "sim.fst"
    f.write_bytes(b"\x00\x01")

    def fake_run(cmd, *args, **kwargs):
        # fst2vcd is invoked as [tool, "-f", <in>, "-o", <out>]; emit VCD there.
        out = cmd[cmd.index("-o") + 1]
        Path(out).write_text(COUNTER_VCD)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("silica.tools.waveform.oss_cad_suite.which",
               return_value="/opt/oss/bin/fst2vcd"), \
         patch("silica.tools.waveform.oss_cad_suite.env_with_suite",
               return_value={}), \
         patch("silica.tools.waveform.subprocess.run", side_effect=fake_run):
        result = read_waveform(str(f), signals=["dut.count"])
    assert result["not_found"] == []
    assert result["signals"][0]["name"] == "tb.dut.count"
    assert {"time": 15, "value": "0010"} in result["signals"][0]["transitions"]


def test_fst_conversion_failure_surfaced(read_waveform, tmp_path):
    f = tmp_path / "sim.fst"
    f.write_bytes(b"\x00\x01")
    failed = MagicMock(returncode=1, stdout="", stderr="not an FST file")
    with patch("silica.tools.waveform.oss_cad_suite.which",
               return_value="/opt/oss/bin/fst2vcd"), \
         patch("silica.tools.waveform.oss_cad_suite.env_with_suite",
               return_value={}), \
         patch("silica.tools.waveform.subprocess.run", return_value=failed):
        result = read_waveform(str(f))
    assert "error" in result
    assert "fst2vcd could not convert" in result["error"]


def test_fst_conversion_cleans_up_temp_vcd(read_waveform, tmp_path):
    """The throwaway VCD from fst2vcd must not linger after the read."""
    f = tmp_path / "sim.fst"
    f.write_bytes(b"\x00\x01")
    created: list[str] = []

    def fake_run(cmd, *args, **kwargs):
        out = cmd[cmd.index("-o") + 1]
        created.append(out)
        Path(out).write_text(COUNTER_VCD)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("silica.tools.waveform.oss_cad_suite.which",
               return_value="/opt/oss/bin/fst2vcd"), \
         patch("silica.tools.waveform.oss_cad_suite.env_with_suite",
               return_value={}), \
         patch("silica.tools.waveform.subprocess.run", side_effect=fake_run):
        read_waveform(str(f))
    assert created and not Path(created[0]).exists()
