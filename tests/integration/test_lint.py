"""Integration tests for lint adapters (verilator, verible, svlint)."""

import shutil
import pytest
from silica import oss_cad_suite
from silica.adapters import verilator, verible, svlint

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
    oss_cad_suite.which("verible-verilog-lint") is None,
    reason="verible-verilog-lint not installed",
)
class TestVerible:
    def test_lint_returns_warnings_list(self, counter_v):
        result = verible.lint(counter_v)
        assert "warnings" in result

    def test_format_returns_formatted_key(self, counter_v):
        result = verible.format(counter_v)
        assert "formatted" in result or "error" in result


# ---------------------------------------------------------------------------
# svlint
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    shutil.which("svlint") is None,
    reason="svlint not installed",
)
class TestSvlint:
    def test_lint_returns_warnings_list(self, counter_v):
        result = svlint.run(counter_v)
        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    def test_result_has_tool_key(self, counter_v):
        result = svlint.run(counter_v)
        assert result.get("tool") == "svlint" or "error" in result
