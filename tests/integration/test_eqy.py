"""Integration tests for the eqy equivalence checking adapter."""

import pytest

from silica import oss_cad_suite
from silica.adapters import eqy

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("eqy") is None or oss_cad_suite.which("yosys") is None,
        reason="eqy or yosys not installed",
    ),
]


def test_equivalent_designs_pass(counter_v):
    result = eqy.run(gold_files=[counter_v], gate_files=[counter_v], top="counter")
    assert result["status"] == "PASS"
    assert result["failures"] == []


def test_inequivalent_designs_fail(counter_v, counter_inequiv_v):
    result = eqy.run(gold_files=[counter_v], gate_files=[counter_inequiv_v], top="counter")
    assert result["status"] == "FAIL"
    assert len(result["failures"]) > 0


def test_result_has_expected_keys(counter_v):
    result = eqy.run(gold_files=[counter_v], gate_files=[counter_v], top="counter")
    for key in ("status", "rc", "failures", "traces", "warnings", "errors",
                "workdir", "raw_output"):
        assert key in result


def test_missing_eqy_file_returns_error():
    result = eqy.run(eqy_file="/nonexistent/path/missing.eqy")
    assert result["status"] == "ERROR"
    assert len(result["errors"]) > 0


def test_generate_eqy_content(counter_v, counter_inequiv_v):
    content = eqy.generate_eqy(
        gold_files=[counter_v], gate_files=[counter_inequiv_v], top="counter"
    )
    assert "[options]" in content
    assert "[gold]" in content
    assert "[gate]" in content
    assert "prep -top counter" in content
    assert "read -formal" in content
