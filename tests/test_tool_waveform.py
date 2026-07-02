"""Tests for silica.tools.waveform (launch_waveform MCP tool)."""

import pytest
from unittest.mock import patch, MagicMock
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


@patch("silica.adapters.verdi.launch", return_value={"launched": True, "viewer": "verdi", "trace": "sim.vcd"})
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
