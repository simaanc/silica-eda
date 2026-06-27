"""Tests for silica.adapters.vc_formal."""

import subprocess
import pytest
from unittest.mock import patch
from conftest import make_proc

from silica.adapters import vc_formal


FAKE_BIN = "/tools/synopsys/vcf"

VCF_PASS = "Overall FV result : PASS\n"
VCF_FAIL = "Overall FV result : FAIL\nFALSIFIED my_prop\n"


@patch("silica.adapters.vc_formal.resolve", return_value=None)
def test_not_found(mock_resolve):
    result = vc_formal.run(files=["dut.sv"], top="top")
    assert result["status"] == "ERROR"


@patch("silica.adapters.vc_formal.subprocess.run")
@patch("silica.adapters.vc_formal.resolve", return_value=FAKE_BIN)
def test_pass(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=VCF_PASS, returncode=0)
    result = vc_formal.run(files=["dut.sv"], top="top")
    assert result["status"] == "PASS"


@patch("silica.adapters.vc_formal.subprocess.run")
@patch("silica.adapters.vc_formal.resolve", return_value=FAKE_BIN)
def test_fail(mock_resolve, mock_run):
    mock_run.return_value = make_proc(stdout=VCF_FAIL, returncode=2)
    result = vc_formal.run(files=["dut.sv"], top="top")
    assert result["status"] == "FAIL"


@patch("silica.adapters.vc_formal.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=300))
@patch("silica.adapters.vc_formal.resolve", return_value=FAKE_BIN)
def test_timeout_propagates(mock_resolve, mock_run):
    with pytest.raises(subprocess.TimeoutExpired):
        vc_formal.run(files=["dut.sv"], top="top")


def test_result_has_required_keys():
    with patch("silica.adapters.vc_formal.resolve", return_value=None):
        result = vc_formal.run(files=["dut.sv"], top="top")
        for key in ("status", "rc", "failures", "traces", "warnings", "errors", "workdir", "raw_output"):
            assert key in result


def test_make_tcl_contains_top():
    tcl = vc_formal._make_tcl("top", ["dut.sv"], "prove", 20)
    assert "top" in tcl
    assert "dut.sv" in tcl
