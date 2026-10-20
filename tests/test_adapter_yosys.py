"""Tests for silica.adapters.yosys."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import make_proc

from silica.adapters import yosys

STAT_OUTPUT = """\
=== top ===
   Number of wires:                 10
   Number of cells:                  3
     $dff                            2
     $lut                            1
"""

YOSYS_WARNING = "Warning: Wire dut.clk is used but never driven.\n"
YOSYS_ERROR = "ERROR: Module not found: undefined_mod\n"


@patch("silica.adapters.yosys.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert result["tool"] == "yosys"
    assert len(result["errors"]) > 0


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_success(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=STAT_OUTPUT, returncode=0)
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == 0
    assert result["tool"] == "yosys"
    assert result["errors"] == []
    assert result["utilization"]["ffs"] == 2
    assert result["utilization"]["luts"] == 1


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_failure(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=YOSYS_ERROR, returncode=1)
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == 1
    assert len(result["errors"]) > 0


@patch("silica.adapters.yosys.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=[], timeout=120))
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_timeout_returns_error(mock_which, mock_run):
    result = yosys.run("top", ["dut.sv"])
    assert result["exit_code"] == -1
    assert any("timed out" in e["message"] for e in result["errors"])


def test_count_cells_dff_and_lut():
    util = yosys._count_cells(STAT_OUTPUT)
    assert util["ffs"] == 2
    assert util["luts"] == 1
    assert util["bram"] == 0
    assert util["dsp"] == 0


# Yosys 0.70 synth_xilinx of a top with one submodule, trimmed: synth_xilinx
# prints its own statistics, then the script's stat prints them again, each
# with per-module blocks followed by the hierarchy total.
_XILINX_MODULE_STAT = """\
=== sub ===

        +----------Local Count, excluding submodules.
        |
       81 cells
        5   CARRY4
       30   FDCE
        2   FDPE
       16   LUT2
        7   LUT6

=== top ===

        +----------Local Count, excluding submodules.
        |
      148 cells
        1   BUFG
       57   FDCE
        6   FDRE
        8   LUT2
        6   LUT6
        1   RAMB18E1
        1   DSP48E1
        1 submodules
        1   sub

=== design hierarchy ===

        +----------Count including submodules.
        |
      229 top
       81 sub

        +----------Count including submodules.
        |
      229 cells
        1   BUFG
        5   CARRY4
       87   FDCE
        2   FDPE
        6   FDRE
       24   LUT2
       13   LUT6
        1   RAMB18E1
        1   DSP48E1
        1 submodules
        1   sub
"""
XILINX_STAT_OUTPUT = (
    "2.50. Printing statistics.\n\n" + _XILINX_MODULE_STAT
    + "\n3. Printing statistics.\n\n" + _XILINX_MODULE_STAT
)


def test_count_cells_xilinx_counts_hierarchy_total_once():
    util = yosys._count_cells(XILINX_STAT_OUTPUT)
    assert util["luts"] == 37
    assert util["ffs"] == 95
    assert util["bram"] == 1
    assert util["dsp"] == 1


@pytest.mark.parametrize("cell,kind", [
    ("SB_LUT4", "luts"), ("SB_DFFER", "ffs"), ("SB_RAM40_4K", "bram"), ("SB_MAC16", "dsp"),
    ("LUT4", "luts"), ("TRELLIS_FF", "ffs"), ("DP16KD", "bram"), ("MULT18X18D", "dsp"),
    ("DFFRE", "ffs"), ("SPX9", "bram"), ("MULT9X9", "dsp"),
    ("LUT6", "luts"), ("FDSE", "ffs"), ("RAMB36E1", "bram"), ("DSP48E1", "dsp"),
    ("$_SDFFCE_PN0P_", "ffs"),
])
def test_count_cells_mapped_primitives(cell, kind):
    util = yosys._count_cells(f"=== top ===\n\n        3   {cell}\n")
    assert util[kind] == 3
    assert sum(util[k] for k in ("luts", "ffs", "bram", "dsp")) == 3


def test_parse_warnings():
    warnings = yosys._parse_warnings(YOSYS_WARNING)
    assert len(warnings) == 1
    assert "Wire" in warnings[0]["message"] or "wire" in warnings[0]["message"].lower()


@pytest.mark.parametrize("target,expected_cmd", [
    ("generic", "synth"),
    ("ice40", "synth_ice40"),
    ("ecp5", "synth_ecp5"),
    ("xilinx", "synth_xilinx"),
    ("gowin", "synth_gowin"),
])
@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_target_selects_synth_command(mock_which, mock_run, target, expected_cmd):
    mock_run.return_value = make_proc(returncode=0)
    yosys.run("top", ["dut.sv"], target=target)
    call_args = mock_run.call_args_list[0].args[0]
    script = call_args[2]
    assert expected_cmd in script


# --- netlist output (FPGA targets) ---

def _run_writing_netlist(*args, **kwargs):
    """Simulate yosys honoring -json: drop netlist.json in the run's cwd."""
    (Path(kwargs["cwd"]) / "netlist.json").write_text("{}")
    return make_proc(stdout=STAT_OUTPUT, returncode=0)


@pytest.mark.parametrize("target", ["ice40", "ecp5", "xilinx", "gowin"])
@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_fpga_target_requests_json_netlist(mock_which, mock_run, target):
    mock_run.return_value = make_proc(returncode=0)
    yosys.run("top", ["dut.sv"], target=target)
    script = mock_run.call_args_list[0].args[0][2]
    assert "-json netlist.json" in script


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_generic_target_has_no_json_flag(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=STAT_OUTPUT, returncode=0)
    result = yosys.run("top", ["dut.sv"], target="generic")
    script = mock_run.call_args_list[0].args[0][2]
    assert "-json" not in script
    assert result["netlist"] is None


@patch("silica.adapters.yosys.subprocess.run", side_effect=_run_writing_netlist)
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_fpga_success_returns_persistent_netlist(mock_which, mock_run):
    result = yosys.run("top", ["dut.sv"], target="ice40")
    assert result["exit_code"] == 0
    assert result["netlist"] is not None
    netlist = Path(result["netlist"])
    assert netlist.exists()
    assert "silica_synth_" in netlist.parent.name
    shutil.rmtree(netlist.parent)


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_fpga_failure_returns_no_netlist(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=YOSYS_ERROR, returncode=1)
    result = yosys.run("top", ["dut.sv"], target="ice40")
    assert result["exit_code"] == 1
    assert result["netlist"] is None


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_fpga_success_without_json_file_returns_no_netlist(mock_which, mock_run):
    # rc==0 but yosys wrote no netlist (e.g. empty design edge case)
    mock_run.return_value = make_proc(stdout=STAT_OUTPUT, returncode=0)
    result = yosys.run("top", ["dut.sv"], target="ice40")
    assert result["exit_code"] == 0
    assert result["netlist"] is None


# --- diagnostic locations -----------------------------------------------------

# Captured from yosys 0.70 (one run per line, trimmed to the diagnostic).
YOSYS_ERRORS_CAPTURED = [
    ("syntax.v:3: ERROR: syntax error, unexpected TOK_ENDMODULE",
     "syntax.v", 3, "syntax error, unexpected TOK_ENDMODULE"),
    ("readmem.v:3: ERROR:Can not open file `nope.hex` for \\$readmemh.",
     "readmem.v", 3, "Can not open file `nope.hex` for \\$readmemh."),
    ("nettype.v:3: ERROR:Identifier `\\nope' is implicitly declared and "
     "`default_nettype is set to none.", "nettype.v", 3, None),
    ("sub_b.v:1: ERROR: Re-definition of module `\\sub'!",
     "sub_b.v", 1, "Re-definition of module `\\sub'!"),
    # No location given: leave it empty, even when an identifier embeds one.
    ("ERROR: Module `\\sub' referenced in module `\\t' in cell `\\u' is not part "
     "of the design.", "", 0, None),
    ("ERROR: Latch inferred for signal `\\t.\\y' from always_comb process "
     "`\\t.$proc$latch.sv:2$1'.", "", 0, None),
]

YOSYS_WARNINGS_CAPTURED = """\
implicit.v:2: Warning: Identifier `\\undeclared_sig' is implicitly declared.
Warning: Wire t.\\undeclared_sig is used but has no driver.
range.v:3: Warning: Range select out of bounds on signal `\\w': Setting result bit to undef.
Warning: reg '\\y' is assigned in a continuous assignment at sv_mixed.sv:5.10-5.15.
Warning: Resizing cell port t.u.a from 4 bits to 2 bits.
ABC: Warning: The network is combinational (run "fraig" or "fraig_sweep").
Warnings: 2 unique messages, 2 total
"""


@pytest.mark.parametrize("line,file,lineno,message", YOSYS_ERRORS_CAPTURED)
def test_extract_error_location(line, file, lineno, message):
    error = yosys._extract_error(f"-- Running command `...' --\n{line}\n")
    assert (error["file"], error["line"], error["severity"]) == (file, lineno, "error")
    assert error["message"] == (message or line.split("ERROR:", 1)[1].strip())


def test_parse_warnings_locations():
    warnings = yosys._parse_warnings(YOSYS_WARNINGS_CAPTURED)
    assert [(w["file"], w["line"]) for w in warnings] == [
        ("implicit.v", 2), ("", 0), ("range.v", 3), ("sv_mixed.sv", 5), ("", 0),
    ]
    assert warnings[0]["message"] == "Identifier `\\undeclared_sig' is implicitly declared."


# Built from yosys's format strings rather than captured runs.
@pytest.mark.parametrize("line,file,lineno", [
    ("ERROR: Port `x' is driven twice at /work/rtl/top.sv:12.5-12.9.", "/work/rtl/top.sv", 12),
    ("C:\\work\\rtl\\top.sv:7: ERROR: syntax error, unexpected ';'", "C:\\work\\rtl\\top.sv", 7),
    # A cell name that looks like a location is not one.
    ("ERROR: Detected loop at $abc$123$auto$blifparse.cc:396:parse_blif$456 in t", "", 0),
])
def test_extract_error_location_forms(line, file, lineno):
    error = yosys._extract_error(line + "\n")
    assert (error["file"], error["line"]) == (file, lineno)


# --- inferred memories --------------------------------------------------------

# Trimmed from `write_json -selected -compat-int` after memory_collect
# (yosys 0.70). INIT is one 0/1/x character per bit.
MEM_REPORT = {
    "modules": {
        "soc": {"cells": {
            "ram": {"type": "$mem_v2", "parameters": {
                "MEMID": "\\ram", "SIZE": 4, "WIDTH": 8, "RD_PORTS": 1, "WR_PORTS": 1,
                "INIT": "00000001" + "x" * 24}},
            "fifo": {"type": "$mem_v2", "parameters": {
                "MEMID": "\\fifo", "SIZE": 16, "WIDTH": 8, "RD_PORTS": 1, "WR_PORTS": 1,
                "INIT": "x" * 128}},
            "tbl": {"type": "$mem_v2", "parameters": {
                "MEMID": "\\tbl", "SIZE": 2, "WIDTH": 4, "RD_PORTS": 1, "WR_PORTS": 0,
                "INIT": "01011010"}},
            "boot": {"type": "$mem_v2", "parameters": {
                "MEMID": "\\boot", "SIZE": 256, "WIDTH": 32, "RD_PORTS": 1, "WR_PORTS": 0,
                "INIT": "x" * 8192}},
        }},
    },
}
MEM_LOG = """\
4.32. Executing MEMORY_LIBMAP pass (mapping memories to cells).
mapping memory soc.ram via $__XILINX_BLOCKRAM_TDP_
mapping memory soc.fifo via $__XILINX_LUTRAM_SDP_
4.36. Executing MEMORY_MAP pass (converting memories to logic and flip-flops).
Mapping memory \\tbl in module \\soc:
"""


def test_parse_memories_types_and_init():
    mems = {m["name"]: m for m in yosys._parse_memories(MEM_REPORT, MEM_LOG)}
    assert (mems["soc.ram"]["type"], mems["soc.ram"]["has_init"]) == ("block_ram", True)
    assert mems["soc.ram"]["mapped_to"] == "$__XILINX_BLOCKRAM_TDP_"
    assert mems["soc.ram"]["bits"] == 32
    assert (mems["soc.fifo"]["type"], mems["soc.fifo"]["has_init"]) == ("distributed_ram", False)
    assert (mems["soc.tbl"]["type"], mems["soc.tbl"]["has_init"]) == ("logic", True)
    assert (mems["soc.boot"]["type"], mems["soc.boot"]["has_init"]) == ("removed", False)


def test_memory_warnings_only_for_empty_roms():
    mems = yosys._parse_memories(MEM_REPORT, MEM_LOG)
    warnings = yosys._memory_warnings(mems)
    assert len(warnings) == 1
    assert "soc.boot" in warnings[0]["message"]
    assert "removed" in warnings[0]["message"]


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_failed_run_reports_error_location(mock_which, mock_run):
    mock_run.return_value = make_proc(
        stdout="readmem.v:3: ERROR:Can not open file `nope.hex` for \\$readmemh.\n",
        returncode=1)
    result = yosys.run("t", ["readmem.v"])
    assert result["errors"] == [{
        "file": "readmem.v", "line": 3, "severity": "error",
        "message": "Can not open file `nope.hex` for \\$readmemh.",
    }]


def test_extract_error_falls_back_without_error_line():
    error = yosys._extract_error("something went wrong\n")
    assert error == {"file": "", "line": 0, "severity": "error",
                     "message": "Yosys synthesis failed"}


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_run_reports_memories_from_second_pass(mock_which, mock_run):
    import json

    def side_effect(cmd, **kwargs):
        if "write_json -selected" in cmd[-1]:
            Path(kwargs["cwd"], "memories.json").write_text(json.dumps(MEM_REPORT))
            return make_proc(returncode=0)
        assert "memory_collect" not in cmd[-1]  # synthesis itself is untouched
        return make_proc(stdout=MEM_LOG + STAT_OUTPUT, returncode=0)

    mock_run.side_effect = side_effect
    result = yosys.run("soc", ["soc.sv"], target="xilinx")
    assert [m["name"] for m in result["memories"]] == ["soc.ram", "soc.fifo", "soc.tbl", "soc.boot"]
    assert any("soc.boot" in w["message"] for w in result["warnings"])


# yosys 0.70 reading a $readmemh whose file doesn't exist.
YOSYS_READMEMH_ERROR = """\
1. Executing Verilog-2005 frontend: /work/rom.v
Parsing Verilog input from `/work/rom.v' to AST representation.
/work/rom.v:4: ERROR:Can not open file `fw_nope.hex` for \\$readmemh.
"""


@patch("silica.adapters.yosys.subprocess.run")
@patch("silica.adapters.yosys.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_readmemh_wrong_path_error_names_the_file(mock_which, mock_run):
    mock_run.return_value = make_proc(stdout=YOSYS_READMEMH_ERROR, returncode=1)
    result = yosys.run("rom", ["rom.v"], target="xilinx")
    assert result["exit_code"] == 1
    assert "fw_nope.hex" in result["errors"][0]["message"]
    assert result["memories"] == []
    mock_run.assert_called_once()  # no memory pass after a failed synthesis
