"""Tests for silica.tools.format (format_rtl MCP tool)."""

from unittest.mock import patch

import pytest
from conftest import MockMCP

from silica.tools import format as format_tool

UNFORMATTED = "module m;\nwire   a;\nendmodule\n"
FORMATTED = "module m;\n  wire a;\nendmodule\n"


@pytest.fixture
def format_rtl():
    mcp = MockMCP()
    format_tool.register(mcp)
    return mcp.tools["format_rtl"]


@pytest.fixture
def in_project(tmp_path, monkeypatch):
    """Temp dir that is also CWD — the confinement root for file tools."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_dry_run_returns_diff_without_writing(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text(UNFORMATTED)
    with patch("silica.tools.format.pick", return_value="verible-verilog-format"), \
         patch("silica.adapters.verible.format_src",
               return_value={"formatted": FORMATTED, "raw_output": ""}):
        result = format_rtl("m.sv", dry_run=True)
    assert result["written"] is False
    assert result["lines_changed"] > 0
    assert "wire a;" in result["diff"]
    assert f.read_text() == UNFORMATTED  # untouched


def test_write_applies_formatting(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text(UNFORMATTED)
    with patch("silica.tools.format.pick", return_value="verible-verilog-format"), \
         patch("silica.adapters.verible.format_src",
               return_value={"formatted": FORMATTED, "raw_output": ""}):
        result = format_rtl("m.sv", dry_run=False)
    assert result["written"] is True
    assert f.read_text() == FORMATTED


def test_already_formatted_is_not_written(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text(FORMATTED)
    with patch("silica.tools.format.pick", return_value="verible-verilog-format"), \
         patch("silica.adapters.verible.format_src",
               return_value={"formatted": FORMATTED, "raw_output": ""}):
        result = format_rtl("m.sv", dry_run=False)
    assert result["written"] is False
    assert result["diff"] == ""


def test_path_escape_rejected(format_rtl, in_project):
    result = format_rtl("../../etc/passwd", dry_run=True)
    assert "error" in result
    assert result["written"] is False


def test_missing_file_errors(format_rtl, in_project):
    result = format_rtl("nope.sv", dry_run=True)
    assert "error" in result


def test_no_formatter_found_errors(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text(UNFORMATTED)
    with patch("silica.tools.format.pick", return_value=None):
        result = format_rtl("m.sv")
    assert "error" in result
    assert "formatter" in result["error"].lower()


def test_syntax_error_surfaced(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text("module broken")
    err = {"error": "verible-verilog-format could not format m.sv: syntax error"}
    with patch("silica.tools.format.pick", return_value="verible-verilog-format"), \
         patch("silica.adapters.verible.format_src", return_value=err):
        result = format_rtl("m.sv")
    assert "error" in result
    assert "syntax" in result["error"]


def test_explicit_disabled_formatter_rejected(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text(UNFORMATTED)
    config = {"tools": {"format": {"enabled": ["nothing"]}}}
    with patch("silica.config.load", return_value=config):
        result = format_rtl("m.sv", tool="verible")
    assert "error" in result
    assert "disabled by config" in result["error"]


def test_unknown_formatter_errors(format_rtl, in_project):
    f = in_project / "m.sv"
    f.write_text(UNFORMATTED)
    result = format_rtl("m.sv", tool="bogus")
    assert "error" in result
    assert "Unknown formatter" in result["error"]
