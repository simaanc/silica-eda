"""Integration tests for the Yosys adapter (synthesis)."""

import pytest
from silica import oss_cad_suite
from silica.adapters import yosys

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("yosys") is None,
        reason="yosys not installed",
    ),
]


def test_generic_synthesis_succeeds(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="generic")
    assert result["exit_code"] == 0
    assert result["tool"] == "yosys"
    assert result["errors"] == []


def test_result_has_expected_keys(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="generic")
    for key in ("exit_code", "tool", "target", "utilization", "timing_summary",
                "warnings", "errors", "raw_output"):
        assert key in result


def test_utilization_has_expected_structure(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="generic")
    util = result["utilization"]
    for key in ("luts", "ffs", "bram", "dsp"):
        assert key in util
    assert util["ffs"] >= 4


def test_ice40_synthesis_succeeds(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="ice40")
    assert result["exit_code"] == 0
    assert result["target"] == "ice40"


def test_bad_rtl_returns_errors(counter_bad_v):
    result = yosys.run(top="counter_bad", files=[counter_bad_v], target="generic")
    assert result["exit_code"] != 0
    assert len(result["errors"]) > 0


def test_nonexistent_top_module_fails(counter_v):
    result = yosys.run(top="no_such_module", files=[counter_v], target="generic")
    assert result["exit_code"] != 0
