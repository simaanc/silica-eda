"""Shared fixtures and helpers for silica-eda tests."""

import os
from subprocess import CompletedProcess

import pytest

# Integration tests skip when a tool isn't installed. A CI job that installs
# tools lists them here (comma-separated registry names, e.g.
# "verible-verilog-lint,svlint") so a broken install fails the run instead of
# silently turning its tests into skips.
_REQUIRED_TOOLS = [t.strip() for t in os.environ.get("SILICA_REQUIRE_TOOLS", "").split(",")
                   if t.strip()]


def pytest_sessionstart(session):
    from silica.detect import resolve

    missing = [t for t in _REQUIRED_TOOLS if resolve(t) is None]
    if missing:
        pytest.exit(f"SILICA_REQUIRE_TOOLS names tools that aren't installed: "
                    f"{', '.join(missing)}", returncode=1)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # Also catch a test that skips for a required tool despite the check above,
    # e.g. because its skip condition looks the tool up differently.
    outcome = yield
    report = outcome.get_result()
    if report.skipped and _REQUIRED_TOOLS:
        reason = str(report.longrepr[-1]) if isinstance(report.longrepr, tuple) else ""
        hit = [t for t in _REQUIRED_TOOLS if t in reason]
        if hit:
            report.outcome = "failed"
            report.longrepr = (f"skipped for a tool in SILICA_REQUIRE_TOOLS "
                               f"({', '.join(hit)}): {reason}")


def make_proc(stdout="", stderr="", returncode=0):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class MockMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator

    def prompt(self):
        def decorator(fn):
            return fn
        return decorator


@pytest.fixture
def mcp():
    return MockMCP()


@pytest.fixture
def sv_file(tmp_path):
    f = tmp_path / "dut.sv"
    f.write_text("module dut(); endmodule")
    return str(f)


@pytest.fixture
def tb_file(tmp_path):
    f = tmp_path / "tb.sv"
    f.write_text("module tb(); endmodule")
    return str(f)


@pytest.fixture
def vhd_file(tmp_path):
    f = tmp_path / "dut.vhd"
    f.write_text("entity dut is end dut;")
    return str(f)


@pytest.fixture
def netlist_file(tmp_path):
    f = tmp_path / "netlist.json"
    f.write_text("{}")
    return str(f)


@pytest.fixture
def sby_file(tmp_path):
    f = tmp_path / "check.sby"
    f.write_text("[options]\nmode prove\n")
    return str(f)


@pytest.fixture
def eqy_file(tmp_path):
    f = tmp_path / "check.eqy"
    f.write_text("[gold]\ngold.sv\n[gate]\ngate.sv\n")
    return str(f)


@pytest.fixture
def bitstream_file(tmp_path):
    f = tmp_path / "top.bit"
    f.write_bytes(b"\x00" * 16)
    return str(f)
