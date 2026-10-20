"""Integration tests for the Yosys adapter (synthesis)."""

import pytest

from silica import oss_cad_suite
from silica.adapters import yosys

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        oss_cad_suite.which("yosys") is None,
        reason="yosys not installed",
    ),
]


def test_generic_synthesis_succeeds(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="generic")
    assert result["exit_code"] == 0
    assert result["tool"] == "yosys"
    assert result["errors"] == []


def test_result_has_expected_keys(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="generic")
    for key in ("exit_code", "tool", "target", "utilization", "timing_summary",
                "warnings", "errors", "raw_output"):
        assert key in result


def test_utilization_has_expected_structure(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="generic")
    util = result["utilization"]
    for key in ("luts", "ffs", "bram", "dsp"):
        assert key in util
    assert util["ffs"] >= 4


def test_ice40_synthesis_succeeds(counter_v):
    result = yosys.run(top="counter", files=[counter_v], target="ice40")
    assert result["exit_code"] == 0
    assert result["target"] == "ice40"


def test_bad_rtl_returns_errors(counter_bad_v):
    result = yosys.run(top="counter_bad", files=[counter_bad_v], target="generic")
    assert result["exit_code"] != 0
    assert len(result["errors"]) > 0


def test_nonexistent_top_module_fails(counter_v):
    result = yosys.run(top="no_such_module", files=[counter_v], target="generic")
    assert result["exit_code"] != 0


def test_error_carries_file_and_line(tmp_path):
    broken = tmp_path / "broken.v"
    broken.write_text(
        "module broken(input a, output y);\n"
        "  assign y = a\n"          # missing semicolon
        "endmodule\n"
    )
    result = yosys.run(top="broken", files=[str(broken)], target="generic")
    assert result["exit_code"] != 0
    (error,) = result["errors"]
    assert error["file"] == str(broken)
    assert error["line"] == 3
    assert "syntax error" in error["message"]


# --- inferred memories -------------------------------------------------------

ROM_V = """\
module rom(input clk, input [9:0] a, output reg [31:0] q,
           input [7:0] wa, input we, input [7:0] d, output reg [7:0] rq);
    reg [31:0] code [0:1023];
    reg [7:0]  scratch [0:255];
    initial $readmemh("{hex}", code);
    always @(posedge clk) q <= code[a];
    always @(posedge clk) begin
        if (we) scratch[wa] <= d;
        rq <= scratch[a[7:0]];
    end
endmodule
"""

# The boot ROM is only loaded under SIM, so synthesis sees an empty ROM.
SIM_ONLY_ROM_V = """\
module boot(input clk, input [7:0] a, output reg [31:0] q);
    reg [31:0] boot [0:255];
`ifdef SIM
    initial $readmemh("{hex}", boot);
`endif
    always @(posedge clk) q <= boot[a];
endmodule
"""


def _write(tmp_path, template, hex_name):
    (tmp_path / "fw.hex").write_text("".join(f"{i:08x}\n" for i in range(1024)))
    src = tmp_path / "top.v"
    src.write_text(template.format(hex=(tmp_path / hex_name).as_posix()))
    return str(src)


def test_readmemh_with_wrong_path_is_reported(tmp_path):
    src = _write(tmp_path, ROM_V, "fw_typo.hex")
    result = yosys.run(top="rom", files=[src], target="xilinx")
    assert result["exit_code"] != 0
    assert "fw_typo.hex" in result["errors"][0]["message"]
    assert "readmemh" in result["errors"][0]["message"]
    assert result["memories"] == []


def test_memories_report_size_mapping_and_init(tmp_path):
    src = _write(tmp_path, ROM_V, "fw.hex")
    result = yosys.run(top="rom", files=[src], target="xilinx")
    assert result["exit_code"] == 0, result["errors"]
    mems = {m["name"]: m for m in result["memories"]}
    assert mems["rom.code"]["depth"] == 1024 and mems["rom.code"]["width"] == 32
    assert mems["rom.code"]["has_init"] is True
    assert mems["rom.code"]["type"] == "block_ram"
    assert mems["rom.scratch"]["has_init"] is False
    assert mems["rom.scratch"]["type"] == "distributed_ram"
    assert not any("no init data" in w["message"] for w in result["warnings"])


def test_rom_loaded_only_in_simulation_is_flagged(tmp_path):
    src = _write(tmp_path, SIM_ONLY_ROM_V, "fw.hex")
    result = yosys.run(top="boot", files=[src], target="xilinx")
    assert result["exit_code"] == 0, result["errors"]
    (boot,) = result["memories"]
    assert boot["name"] == "boot.boot" and boot["has_init"] is False
    assert any("boot.boot" in w["message"] and "no init data" in w["message"]
               for w in result["warnings"])
