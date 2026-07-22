"""Tests for silica.tools.coverage (read_coverage) and lcov parsing."""

from unittest.mock import patch

import pytest
from conftest import MockMCP

from silica.tools import coverage
from silica.tools.coverage import _parse_lcov

LCOV = """\
TN:
SF:/proj/dut.sv
DA:3,10
DA:4,0
DA:5,2
end_of_record
SF:/proj/sub.sv
DA:1,0
DA:2,0
end_of_record
"""


@pytest.fixture
def read_coverage():
    mcp = MockMCP()
    coverage.register(mcp)
    return mcp.tools["read_coverage"]


# --- lcov parser ---

def test_parse_lcov_per_file_and_total():
    files, total = _parse_lcov(LCOV)
    dut = next(f for f in files if f["file"].endswith("dut.sv"))
    assert dut["lines_total"] == 3
    assert dut["lines_covered"] == 2
    assert dut["uncovered_lines"] == [4]
    assert dut["coverage_pct"] == pytest.approx(66.7, abs=0.1)

    # overall: 2 covered of 5 total
    assert total["lines_total"] == 5
    assert total["lines_covered"] == 2
    assert total["coverage_pct"] == pytest.approx(40.0, abs=0.1)


def test_parse_lcov_repeated_da_keeps_max():
    files, _ = _parse_lcov("SF:/x.sv\nDA:1,0\nDA:1,7\nend_of_record\n")
    assert files[0]["lines_covered"] == 1


def test_parse_lcov_empty_is_full():
    files, total = _parse_lcov("")
    assert files == []
    assert total["coverage_pct"] == 100.0


# --- read_coverage tool ---

def test_read_coverage_success(read_coverage, tmp_path):
    dat = tmp_path / "coverage.dat"
    dat.write_text("dummy")
    with patch("silica.adapters.verilator.coverage_info",
               return_value={"info": LCOV}):
        result = read_coverage(str(dat))
    assert result["file_count"] == 2
    assert result["total"]["lines_covered"] == 2


def test_read_coverage_caps_uncovered(read_coverage, tmp_path):
    dat = tmp_path / "coverage.dat"
    dat.write_text("dummy")
    big = "SF:/x.sv\n" + "".join(f"DA:{i},0\n" for i in range(1, 21)) + "end_of_record\n"
    with patch("silica.adapters.verilator.coverage_info",
               return_value={"info": big}):
        result = read_coverage(str(dat), max_uncovered=5)
    f = result["files"][0]
    assert len(f["uncovered_lines"]) == 5
    assert f["uncovered_truncated"] is True


def test_read_coverage_missing_file(read_coverage):
    result = read_coverage("/nope/coverage.dat")
    assert "error" in result


def test_read_coverage_tool_error_surfaced(read_coverage, tmp_path):
    dat = tmp_path / "coverage.dat"
    dat.write_text("dummy")
    with patch("silica.adapters.verilator.coverage_info",
               return_value={"error": "verilator_coverage not found"}):
        result = read_coverage(str(dat))
    assert "error" in result
    assert "verilator_coverage" in result["error"]
