"""Integration tests for the SymbiYosys (sby) formal verification adapter."""

import pytest

from silica import oss_cad_suite
from silica.adapters import sby

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("sby") is None or oss_cad_suite.which("yosys") is None,
        reason="sby or yosys not installed",
    ),
]


def _write_sby(tmp_path, rtl_file, top):
    content = sby.generate_sby(files=[rtl_file], top=top, mode="prove", depth=10)
    sby_file = tmp_path / f"{top}.sby"
    sby_file.write_text(content)
    return str(sby_file)


def test_trivially_true_assertion_passes(tmp_path, counter_formal_v):
    sby_file = _write_sby(tmp_path, counter_formal_v, "counter_formal")
    result = sby.run(sby_file)
    assert result["status"] == "PASS"
    assert result["failures"] == []


def test_failing_assertion_detected(tmp_path, counter_fail_v):
    sby_file = _write_sby(tmp_path, counter_fail_v, "counter_fail")
    result = sby.run(sby_file)
    assert result["status"] == "FAIL"
    assert len(result["failures"]) > 0


def test_result_has_expected_keys(tmp_path, counter_formal_v):
    sby_file = _write_sby(tmp_path, counter_formal_v, "counter_formal")
    result = sby.run(sby_file)
    for key in ("status", "rc", "failures", "traces", "warnings", "errors",
                "workdir", "raw_output"):
        assert key in result


def test_missing_sby_file_returns_error():
    result = sby.run("/nonexistent/path/missing.sby")
    assert result["status"] == "ERROR"
    assert len(result["errors"]) > 0


def test_generate_sby_content(counter_formal_v):
    content = sby.generate_sby(
        files=[counter_formal_v], top="counter_formal", mode="bmc", depth=5
    )
    assert "[options]" in content
    assert "mode bmc" in content
    assert "depth 5" in content
    assert "[engines]" in content
    assert "[script]" in content
    assert "counter_formal" in content
    assert "[files]" in content
