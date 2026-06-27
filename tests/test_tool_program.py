"""Tests for silica.tools.program (program_device MCP tool)."""

import pytest
from unittest.mock import patch
from conftest import MockMCP

from silica.tools import program


PROG_SUCCESS = {
    "tool": "openFPGALoader", "exit_code": 0,
    "success": True, "errors": [], "raw_output": "programmed",
}
PROG_FAIL = {
    "tool": "openFPGALoader", "exit_code": 1,
    "success": False, "errors": [{"message": "device not found"}], "raw_output": "Error",
}
PROG_NOT_FOUND = {
    "tool": "openFPGALoader", "exit_code": -1,
    "success": False, "errors": [{"message": "not found"}], "raw_output": "",
}


@pytest.fixture
def program_device():
    mcp = MockMCP()
    program.register(mcp)
    return mcp.tools["program_device"]


@patch("silica.adapters.openfpgaloader.run", return_value=PROG_SUCCESS)
@patch("silica.tools.program.pick", return_value="openfpgaloader")
def test_auto_picks_openfpgaloader(mock_pick, mock_run, program_device, bitstream_file):
    result = program_device(bitstream_file, tool="auto")
    assert result["success"] is True
    mock_run.assert_called_once()


@patch("silica.adapters.openfpgaloader.run", return_value=PROG_SUCCESS)
def test_openfpgaloader_named_lowercase(mock_run, program_device, bitstream_file):
    result = program_device(bitstream_file, tool="openfpgaloader")
    assert result["success"] is True


@patch("silica.adapters.openfpgaloader.run", return_value=PROG_SUCCESS)
def test_openfpgaloader_named_camelcase(mock_run, program_device, bitstream_file):
    result = program_device(bitstream_file, tool="openFPGALoader")
    assert result["success"] is True


@patch("silica.adapters.openfpgaloader.run", return_value=PROG_FAIL)
def test_failure_propagated(mock_run, program_device, bitstream_file):
    result = program_device(bitstream_file, tool="openfpgaloader")
    assert result["success"] is False
    assert result["exit_code"] == 1


def test_unknown_tool_returns_error(program_device, bitstream_file):
    result = program_device(bitstream_file, tool="bogus")
    assert result["exit_code"] == -1
    assert result["success"] is False


@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=None)
@patch("silica.tools.program.pick", return_value=None)
def test_auto_no_tool_returns_error(mock_pick, mock_which, program_device, bitstream_file):
    result = program_device(bitstream_file, tool="auto")
    assert result["exit_code"] == -1
    assert result["success"] is False


@patch("silica.adapters.openfpgaloader.run", return_value=PROG_SUCCESS)
def test_passes_board_and_cable(mock_run, program_device, bitstream_file):
    program_device(bitstream_file, board="arty", cable="ft232", tool="openfpgaloader")
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs.get("board") == "arty"
    assert call_kwargs.get("cable") == "ft232"


@patch("silica.adapters.openfpgaloader.run", return_value=PROG_SUCCESS)
def test_passes_spi_flash(mock_run, program_device, bitstream_file):
    program_device(bitstream_file, spi_flash=True, tool="openfpgaloader")
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs.get("spi_flash") is True
