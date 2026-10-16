"""Integration tests for the cocotb runner adapter (cocotb + Icarus)."""

import importlib.util

import pytest

from silica import oss_cad_suite
from silica.adapters import cocotb_runner

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        importlib.util.find_spec("cocotb") is None,
        reason="cocotb not installed",
    ),
    pytest.mark.skipif(
        oss_cad_suite.which("iverilog") is None,
        reason="iverilog not installed",
    ),
]

COUNTER_TESTS = """\
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


@cocotb.test()
async def counts_up(dut):
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 3)
    await RisingEdge(dut.clk)
    assert int(dut.count.value) > 0


@cocotb.test()
async def stays_zero(dut):
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 3)
    assert int(dut.count.value) == 0
"""


def test_reports_per_test_results(tmp_path, counter_v):
    test_module = tmp_path / "test_counter_cocotb.py"
    test_module.write_text(COUNTER_TESTS)
    result = cocotb_runner.run(
        sources=[counter_v],
        test_module=str(test_module),
        toplevel="counter",
        simulator="icarus",
    )
    assert "error" not in result, result.get("error")
    statuses = {t["name"]: t["status"] for t in result["tests"]}
    assert statuses == {"counts_up": "passed", "stays_zero": "failed"}
    assert (result["passed"], result["failed"]) == (1, 1)
