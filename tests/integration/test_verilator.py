"""Integration tests for the Verilator adapter."""

import pytest
from silica import oss_cad_suite
from silica.adapters import verilator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("verilator") is None,
        reason="verilator not installed",
    ),
]


def test_successful_simulation(counter_v, counter_tb_v):
    result = verilator.run(dut=counter_v, testbench=counter_tb_v, top="counter_tb")
    assert result["exit_code"] == 0
    assert result["errors"] == []


def test_compile_error_on_bad_rtl(counter_bad_v, counter_tb_v):
    result = verilator.run(dut=counter_bad_v, testbench=counter_tb_v, top="counter_tb")
    assert result["exit_code"] != 0
    assert len(result["errors"]) > 0


def test_result_has_expected_keys(counter_v, counter_tb_v):
    result = verilator.run(dut=counter_v, testbench=counter_tb_v, top="counter_tb")
    for key in ("exit_code", "errors", "warnings", "raw_stdout", "raw_stderr", "trace_vcd"):
        assert key in result


def test_lint_only_clean_file(counter_v):
    result = verilator.lint_only(counter_v)
    assert result["exit_code"] == 0
    assert result["errors"] == []


def test_lint_only_bad_file(counter_bad_v):
    result = verilator.lint_only(counter_bad_v)
    assert result["exit_code"] != 0
    assert len(result["errors"]) > 0
