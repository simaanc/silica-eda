"""Tests for silica.tools.project (project MCP tools)."""

from unittest.mock import patch

import pytest
from conftest import MockMCP

from silica.tools import project


@pytest.fixture
def tools():
    mcp = MockMCP()
    project.register(mcp)
    return mcp.tools


@pytest.fixture
def in_project(tmp_path, monkeypatch):
    """A temp dir that is also the CWD, i.e. the confinement root for the file tools."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "top.sv").write_text("module top(); endmodule")
    (tmp_path / "rtl" / "sub.v").write_text("module sub(); endmodule")
    (tmp_path / "rtl" / "pkg.svh").write_text("`define FOO 1")
    (tmp_path / "constraints").mkdir(parents=True, exist_ok=True)
    (tmp_path / "constraints" / "top.xdc").write_text("set_property PACKAGE_PIN A1 [get_ports clk]")
    return str(tmp_path)


# --- get_project_structure ---

def test_get_structure_finds_sv_files(tools, project_root):
    result = tools["get_project_structure"](root=project_root)
    assert "rtl_files" in result
    sv_files = [f for f in result["rtl_files"] if f.endswith(".sv")]
    assert len(sv_files) >= 1


def test_get_structure_finds_constraint_files(tools, project_root):
    result = tools["get_project_structure"](root=project_root)
    xdc_files = [f for f in result.get("constraint_files", []) if f.endswith(".xdc")]
    assert len(xdc_files) >= 1


def test_get_structure_nonexistent_root(tools):
    result = tools["get_project_structure"](root="/nonexistent/path")
    assert "rtl_files" in result
    assert result["file_count"] == 0 or "error" in result


def test_get_structure_file_count(tools, project_root):
    result = tools["get_project_structure"](root=project_root)
    assert result["file_count"] >= 2


# --- read_rtl ---

def test_read_rtl_success(tools, in_project):
    f = in_project / "dut.sv"
    f.write_text("module dut();\nendmodule\n")
    result = tools["read_rtl"](file=str(f))
    assert "content" in result
    assert "module dut" in result["content"]
    assert result["total_lines"] == 2


def test_read_rtl_missing_file(tools, in_project):
    result = tools["read_rtl"](file="nonexistent/dut.sv")
    assert "error" in result


def test_read_rtl_with_line_range(tools, in_project):
    f = in_project / "dut.sv"
    lines = [f"// line {i}\n" for i in range(1, 21)]
    f.write_text("".join(lines))
    result = tools["read_rtl"](file=str(f), start_line=5, end_line=10)
    assert "content" in result
    assert result["start_line"] == 5
    assert result["end_line"] == 10


def test_read_rtl_rejects_escape_outside_project(tools, in_project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.sv"
    outside.write_text("module secret(); endmodule\n")
    result = tools["read_rtl"](file=str(outside))
    assert "escapes the project directory" in result["error"]
    assert result["content"] == ""


def test_read_rtl_rejects_dotdot_traversal(tools, in_project):
    result = tools["read_rtl"](file="../../etc/passwd")
    assert "escapes the project directory" in result.get("error", "")


# --- write_rtl ---

def test_write_rtl_dry_run_does_not_write(tools, in_project):
    f = in_project / "new.sv"
    result = tools["write_rtl"](file=str(f), content="module new(); endmodule", dry_run=True)
    assert result["dry_run"] is True
    assert not f.exists()


def test_write_rtl_actually_writes(tools, in_project):
    f = in_project / "new.sv"
    result = tools["write_rtl"](file=str(f), content="module new(); endmodule", dry_run=False)
    assert result["written"] is True
    assert f.exists()
    assert "module new" in f.read_text()


def test_write_rtl_relative_path_writes_in_project(tools, in_project):
    result = tools["write_rtl"](file="rtl/new.sv", content="module new(); endmodule", dry_run=False)
    assert result["written"] is True
    assert (in_project / "rtl" / "new.sv").exists()


def test_write_rtl_diff_present(tools, in_project):
    f = in_project / "dut.sv"
    f.write_text("module dut(); endmodule\n")
    result = tools["write_rtl"](file=str(f), content="module dut2(); endmodule\n", dry_run=True)
    assert "diff" in result


def test_write_rtl_rejects_escape_outside_project(tools, in_project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "evil.sv"
    result = tools["write_rtl"](file=str(outside), content="module evil(); endmodule",
                                dry_run=False)
    assert result["written"] is False
    assert "escapes the project directory" in result["error"]
    assert not outside.exists()


def test_write_rtl_rejects_dotdot_traversal_even_in_dry_run(tools, in_project):
    # dry_run diffs the existing file content, so an escape would leak reads too.
    result = tools["write_rtl"](file="../evil.sv", content="x", dry_run=True)
    assert result["written"] is False
    assert "escapes the project directory" in result["error"]
    assert result["diff"] == ""


# --- search_rtl ---

def test_search_rtl_finds_symbol(tools, tmp_path, in_project):
    (tmp_path / "dut.sv").write_text("module dut();\n  wire clk;\nendmodule\n")
    result = tools["search_rtl"](query="clk", root=str(tmp_path))
    assert result["match_count"] >= 1
    assert any("clk" in m["context"] for m in result["matches"])


def test_search_rtl_no_matches(tools, tmp_path, in_project):
    (tmp_path / "dut.sv").write_text("module dut(); endmodule\n")
    result = tools["search_rtl"](query="TOTALLY_UNIQUE_STRING_XYZ123", root=str(tmp_path))
    assert result["match_count"] == 0
    assert result["matches"] == []


def test_search_rtl_truncation_flagged(tools, tmp_path, in_project):
    body = "\n".join(f"wire clk_{i};" for i in range(60))
    (tmp_path / "dut.sv").write_text(f"module dut();\n{body}\nendmodule\n")
    result = tools["search_rtl"](query="clk_", root=str(tmp_path))
    assert result["match_count"] == 60
    assert len(result["matches"]) == 50
    assert result["truncated"] is True


def test_search_rtl_not_truncated_when_under_cap(tools, tmp_path, in_project):
    (tmp_path / "dut.sv").write_text("module dut();\n  wire clk;\nendmodule\n")
    result = tools["search_rtl"](query="clk", root=str(tmp_path))
    assert result["truncated"] is False


def test_search_rtl_scoped_to_sv(tools, tmp_path, in_project):
    (tmp_path / "dut.sv").write_text("module dut(); endmodule\n")
    (tmp_path / "dut.v").write_text("module dut_v(); endmodule\n")
    result = tools["search_rtl"](query="module", root=str(tmp_path), scope="sv")
    files = {m["file"] for m in result["matches"]}
    assert all(f.endswith(".sv") for f in files)



def test_search_rtl_rejects_root_outside_project(tools, in_project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.sv").write_text("module secret(); wire clk; endmodule\n")
    result = tools["search_rtl"](query="clk", root=str(outside))
    assert "escapes the project directory" in result["error"]
    assert result["matches"] == []


def test_get_structure_rejects_root_outside_project(tools, in_project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.sv").write_text("module secret(); endmodule\n")
    result = tools["get_project_structure"](root=str(outside))
    assert "escapes the project directory" in result["error"]
    assert result["rtl_files"] == []

# --- get_constraints ---

def test_get_constraints_xdc(tools, project_root):
    import os
    xdc = os.path.join(project_root, "constraints", "top.xdc")
    result = tools["get_constraints"](file=xdc)
    assert result["format"] == "xdc"
    assert "content" in result


def test_get_constraints_missing(tools, in_project):
    result = tools["get_constraints"](file="nonexistent/top.xdc")
    assert "error" in result


def test_get_constraints_rejects_escape_outside_project(tools, in_project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "top.xdc"
    outside.write_text("# constraints\n")
    result = tools["get_constraints"](file=str(outside))
    assert "escapes the project directory" in result["error"]
    assert result["content"] == ""


@pytest.mark.parametrize("ext,expected_fmt", [
    (".xdc", "xdc"), (".lpf", "lpf"), (".sdc", "sdc"), (".pdc", "pdc"),
])
def test_get_constraints_format_detection(tools, in_project, ext, expected_fmt):
    f = in_project / f"constraints{ext}"
    f.write_text("# constraints\n")
    result = tools["get_constraints"](file=str(f))
    assert result["format"] == expected_fmt


# --- project_root resolution ---

def test_project_root_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("SILICA_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    with patch("silica.config.load", return_value={}):
        assert project.project_root() == tmp_path.resolve()


def test_project_root_from_config(tmp_path, monkeypatch):
    monkeypatch.delenv("SILICA_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)  # CWD is elsewhere; config must win
    proj = tmp_path / "proj"
    proj.mkdir()
    config = {"project": {"root": str(proj)}}
    with patch("silica.config.load", return_value=config):
        assert project.project_root() == proj.resolve()


def test_project_root_env_overrides_config(tmp_path, monkeypatch):
    env_root = tmp_path / "env_root"
    env_root.mkdir()
    cfg_root = tmp_path / "cfg_root"
    cfg_root.mkdir()
    monkeypatch.setenv("SILICA_PROJECT_ROOT", str(env_root))
    config = {"project": {"root": str(cfg_root)}}
    with patch("silica.config.load", return_value=config):
        assert project.project_root() == env_root.resolve()


def test_project_root_ignores_nonexistent_config_root(tmp_path, monkeypatch):
    monkeypatch.delenv("SILICA_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    config = {"project": {"root": str(tmp_path / "does_not_exist")}}
    with patch("silica.config.load", return_value=config):
        assert project.project_root() == tmp_path.resolve()


def test_confine_root_follows_configured_project_root(tools, tmp_path, monkeypatch):
    """A file inside the configured project root is allowed even when CWD is elsewhere."""
    monkeypatch.delenv("SILICA_PROJECT_ROOT", raising=False)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "dut.sv").write_text("module dut(); endmodule\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    config = {"project": {"root": str(proj)}}
    with patch("silica.config.load", return_value=config):
        result = tools["read_rtl"](file=str(proj / "dut.sv"))
        assert "module dut" in result["content"]
        # A file under the old CWD now escapes the configured root.
        escape = tools["read_rtl"](file=str(elsewhere / "x.sv"))
        assert "escapes the project directory" in escape["error"]


def test_confine_resolves_relative_paths_against_project_root(tools, tmp_path, monkeypatch):
    """A relative path means relative to the project root, not the server's CWD."""
    monkeypatch.delenv("SILICA_PROJECT_ROOT", raising=False)
    proj = tmp_path / "proj"
    (proj / "rtl").mkdir(parents=True)
    (proj / "rtl" / "dut.sv").write_text("module dut(); endmodule\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    config = {"project": {"root": str(proj)}}
    with patch("silica.config.load", return_value=config):
        result = tools["read_rtl"](file="rtl/dut.sv")
        assert "module dut" in result["content"]
        escape = tools["read_rtl"](file="../elsewhere/x.sv")
        assert "escapes the project directory" in escape["error"]
