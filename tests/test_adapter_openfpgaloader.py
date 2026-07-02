"""Tests for silica.adapters.openfpgaloader."""

from unittest.mock import patch

from conftest import make_proc

from silica.adapters import openfpgaloader

FAKE_BIN = "/usr/bin/openFPGALoader"


@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which, bitstream_file):
    result = openfpgaloader.run(bitstream_file)
    assert result["exit_code"] == -1
    assert result["success"] is False


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run")
def test_success(mock_run, mock_which, mock_env, bitstream_file):
    mock_run.return_value = make_proc(stdout="Bitfile programmed successfully", returncode=0)
    result = openfpgaloader.run(bitstream_file)
    assert result["exit_code"] == 0
    assert result["success"] is True
    assert result["tool"] == "openFPGALoader"
    assert result["errors"] == []


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run")
def test_failure(mock_run, mock_which, mock_env, bitstream_file):
    mock_run.return_value = make_proc(stderr="Error: device not found\n", returncode=1)
    result = openfpgaloader.run(bitstream_file)
    assert result["exit_code"] == 1
    assert result["success"] is False
    assert len(result["errors"]) > 0


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run")
def test_board_flag(mock_run, mock_which, mock_env, bitstream_file):
    mock_run.return_value = make_proc(returncode=0)
    openfpgaloader.run(bitstream_file, board="arty")
    cmd = mock_run.call_args[0][0]
    assert "-b" in cmd
    assert "arty" in cmd


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run")
def test_spi_flash_flag(mock_run, mock_which, mock_env, bitstream_file):
    mock_run.return_value = make_proc(returncode=0)
    openfpgaloader.run(bitstream_file, spi_flash=True)
    cmd = mock_run.call_args[0][0]
    assert "-f" in cmd


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=60))
def test_timeout(mock_run, mock_which, mock_env, bitstream_file):
    result = openfpgaloader.run(bitstream_file)
    assert result["exit_code"] == -1
    assert result["success"] is False
