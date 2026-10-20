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


# openFPGALoader v1.1.1 loading a bitstream whose header declares a zero
# length into an Arty A7: it exits 0, but the device never asserts DONE.
OFL_XILINX_DONE_LOW = """\
Jtag frequency : requested 10.00MHz   -> real 10.00MHz
Open file arty.bit DONE
Parse file Unknown key Generator
File is longer than bitstream length declared in the header: 3825788 vs 0
DONE
load program

Load SRAM: [] -nan%

Done
Shift IR 11
ir: 1 isc_done 0 isc_ena 0 init 1 done 0
Register raw value: 0x5000190c
CRC Error       No CRC error
INIT Complete   0x1
Done            0x0
"""

OFL_XILINX_DONE_HIGH = """\
Jtag frequency : requested 10.00MHz   -> real 10.00MHz
Open file arty.bit DONE
Parse file Unknown key Generator
DONE
load program

Load SRAM: [===================================================] 100.00%

Done
Shift IR 35
ir: 1 isc_done 1 isc_ena 0 init 1 done 1
"""


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run")
def test_xilinx_done_low_is_failure_despite_exit_0(mock_run, mock_which, mock_env, bitstream_file):
    mock_run.return_value = make_proc(stdout=OFL_XILINX_DONE_LOW, returncode=0)
    result = openfpgaloader.run(bitstream_file, board="arty_a7_100t")
    assert result["exit_code"] == 0
    assert result["success"] is False
    assert "DONE" in result["errors"][0]["message"]


@patch("silica.adapters.openfpgaloader.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.openfpgaloader.oss_cad_suite.which", return_value=FAKE_BIN)
@patch("silica.adapters.openfpgaloader.subprocess.run")
def test_xilinx_done_high_is_success(mock_run, mock_which, mock_env, bitstream_file):
    mock_run.return_value = make_proc(stdout=OFL_XILINX_DONE_HIGH, returncode=0)
    result = openfpgaloader.run(bitstream_file, board="arty_a7_100t")
    assert result["success"] is True
    assert result["errors"] == []


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
@patch("silica.adapters.openfpgaloader.subprocess.run",
       side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=60))
def test_timeout(mock_run, mock_which, mock_env, bitstream_file):
    result = openfpgaloader.run(bitstream_file)
    assert result["exit_code"] == -1
    assert result["success"] is False
