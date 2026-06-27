"""Tests for silica.adapters.verdi."""

import pytest
from unittest.mock import patch, MagicMock

from silica.adapters import verdi


FAKE_BIN = "/tools/synopsys/verdi"


@patch("silica.adapters.verdi.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = verdi.launch("sim.vcd")
    assert result["launched"] is False
    assert "error" in result


@patch("silica.adapters.verdi.subprocess.Popen")
@patch("silica.adapters.verdi.resolve", return_value=FAKE_BIN)
def test_launch_vcd(mock_resolve, mock_popen):
    mock_popen.return_value = MagicMock()
    result = verdi.launch("sim.vcd")
    assert result["launched"] is True
    assert result["viewer"] == "verdi"
    assert result["trace"] == "sim.vcd"


@patch("silica.adapters.verdi.subprocess.Popen")
@patch("silica.adapters.verdi.resolve", return_value=FAKE_BIN)
def test_launch_fsdb_uses_ssf_flag(mock_resolve, mock_popen):
    mock_popen.return_value = MagicMock()
    verdi.launch("sim.fsdb")
    cmd = mock_popen.call_args[0][0]
    assert "-ssf" in cmd
    assert "sim.fsdb" in cmd


@patch("silica.adapters.verdi.subprocess.Popen")
@patch("silica.adapters.verdi.resolve", return_value=FAKE_BIN)
def test_launch_non_fsdb_no_ssf_flag(mock_resolve, mock_popen):
    mock_popen.return_value = MagicMock()
    verdi.launch("sim.vcd")
    cmd = mock_popen.call_args[0][0]
    assert "-ssf" not in cmd


@patch("silica.adapters.verdi.subprocess.Popen", side_effect=OSError("not found"))
@patch("silica.adapters.verdi.resolve", return_value=FAKE_BIN)
def test_popen_oserror_propagates(mock_resolve, mock_popen):
    import pytest
    with pytest.raises(OSError):
        verdi.launch("sim.vcd")
