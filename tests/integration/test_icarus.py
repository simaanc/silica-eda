"""Integration tests for the Icarus Verilog adapter (iverilog + vvp)."""

import pytest

from silica import oss_cad_suite
from silica.adapters import icarus

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("iverilog") is None,
        reason="iverilog not installed",
    ),
]


def test_successful_simulation(counter_v, counter_tb_v):
    result = icarus.run(dut=counter_v, testbench=counter_tb_v, top="counter_tb")
    assert result["exit_code"] == 0
    assert result["errors"] == []
    assert "PASS" in result["raw_stdout"]


def test_compile_error_on_bad_rtl(counter_bad_v, counter_tb_v):
    result = icarus.run(dut=counter_bad_v, testbench=counter_tb_v)
    assert result["exit_code"] != 0
    assert len(result["errors"]) > 0
    assert all(e["severity"] == "error" for e in result["errors"])


def test_result_has_expected_keys(counter_v, counter_tb_v):
    result = icarus.run(dut=counter_v, testbench=counter_tb_v, top="counter_tb")
    for key in ("exit_code", "errors", "warnings", "raw_stdout", "raw_stderr"):
        assert key in result


def test_trace_key_present(counter_v, counter_tb_v):
    result = icarus.run(dut=counter_v, testbench=counter_tb_v, top="counter_tb", trace=True)
    assert result["exit_code"] == 0
    assert "trace_vcd" in result
