"""Shared fixtures and helpers for silica-eda tests."""

import pytest
from subprocess import CompletedProcess


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
