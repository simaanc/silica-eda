"""Integration tests for lint adapters (verilator, verible, svlint)."""

import pytest

from silica import oss_cad_suite
from silica.adapters import svlint, verible, verilator
from silica.detect import resolve

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Verilator lint_only
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    oss_cad_suite.which("verilator") is None,
    reason="verilator not installed",
)
class TestVerilatorLint:
    def test_clean_file_no_errors(self, counter_v):
        result = verilator.lint_only(counter_v)
        assert result["exit_code"] == 0
        assert result["errors"] == []

    def test_bad_file_reports_errors(self, counter_bad_v):
        result = verilator.lint_only(counter_bad_v)
        assert result["exit_code"] != 0
        assert len(result["errors"]) > 0
        assert all(e["line"] > 0 for e in result["errors"])


# ---------------------------------------------------------------------------
# Verible
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    resolve("verible-verilog-lint") is None,
    reason="verible-verilog-lint not installed",
)
class TestVerible:
    def test_lint_returns_warnings_list(self, counter_v):
        result = verible.run(counter_v)
        assert "error" not in result, result.get("error")
        assert result["tool"] == "verible-verilog-lint"
        # counter.v's 4'b1 has fewer digits than its width.
        assert any(w["rule_id"] == "undersized-binary-literal" and w["line"] > 0
                   for w in result["warnings"]), result["warnings"]

    @pytest.mark.skipif(resolve("verible-verilog-format") is None,
                        reason="verible-verilog-format not installed")
    def test_format_returns_formatted_key(self, counter_v):
        result = verible.format_src(counter_v)
        assert "error" not in result, result.get("error")
        assert "module counter" in result["formatted"]


# ---------------------------------------------------------------------------
# svlint
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    resolve("svlint") is None,
    reason="svlint not installed",
)
class TestSvlint:
    def test_lint_returns_warnings_list(self, counter_v):
        result = svlint.run(counter_v)
        assert "error" not in result, result.get("error")
        assert isinstance(result["warnings"], list)
        assert all(w["line"] > 0 and w["rule_id"] for w in result["warnings"])

    def test_result_has_tool_key(self, counter_v):
        result = svlint.run(counter_v)
        assert result.get("tool") == "svlint"
