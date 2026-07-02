"""Integration tests for the GHDL adapter (VHDL simulation)."""

import os

import pytest

from silica import oss_cad_suite
from silica.adapters import ghdl

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("ghdl") is None,
        reason="ghdl not installed",
    ),
]


def test_successful_simulation(counter_vhd, counter_tb_vhd):
    result = ghdl.run(
        dut=counter_vhd,
        testbench=counter_tb_vhd,
        top="counter_tb",
        stop_time="200ns",
    )
    assert result["exit_code"] == 0
    assert result["errors"] == []


def test_result_has_expected_keys(counter_vhd, counter_tb_vhd):
    result = ghdl.run(
        dut=counter_vhd,
        testbench=counter_tb_vhd,
        top="counter_tb",
        stop_time="100ns",
    )
    for key in ("exit_code", "errors", "warnings", "raw_stdout", "raw_stderr", "trace_vcd"):
        assert key in result


def test_trace_produces_vcd(counter_vhd, counter_tb_vhd):
    result = ghdl.run(
        dut=counter_vhd,
        testbench=counter_tb_vhd,
        top="counter_tb",
        stop_time="100ns",
        trace=True,
    )
    assert result["exit_code"] == 0
    assert result["trace_vcd"] is not None
    assert os.path.exists(result["trace_vcd"])


def test_analyze_error_on_bad_vhdl(tmp_path, counter_tb_vhd):
    bad_vhd = tmp_path / "bad.vhd"
    bad_vhd.write_text("this is not valid VHDL !! @@\n")
    result = ghdl.run(dut=str(bad_vhd), testbench=counter_tb_vhd, top="counter_tb")
    assert result["exit_code"] != 0
    assert len(result["errors"]) > 0
