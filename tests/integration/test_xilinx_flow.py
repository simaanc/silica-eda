"""synthesize -> run_place_route for Xilinx 7-series with openXC7 (nextpnr-xilinx
and fpga-as), on the Arty A7 pinout, through the MCP tools.

Needs yosys, nextpnr-xilinx and fpga-as, PRJXRAY_DB_DIR, and a chip database
for one of the parts below in ARTIX7_CHIPDB or NEXTPNR_XILINX_CHIPDB_DIR (see
docs/eda-tools.md). The openxc7 CI workflow provides all of these.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from silica.adapters import nextpnr
from silica.detect import resolve
from silica.tools import place_route, synthesis

# Arty A7-35T and A7-100T: same package and pins, so one XDC fits both.
_PARTS = ["xc7a35tcsg324-1", "xc7a100tcsg324-1"]
_PART = next((p for p in _PARTS if nextpnr._xilinx_chipdb(p)), None)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        any(resolve(t) is None for t in ("yosys", "nextpnr-xilinx", "fpga-as")),
        reason="yosys, nextpnr-xilinx or fpga-as not installed",
    ),
    pytest.mark.skipif(
        _PART is None or not os.environ.get("PRJXRAY_DB_DIR"),
        reason="nextpnr-xilinx chip database or PRJXRAY_DB_DIR not found",
    ),
]

BLINKY_V = """\
module blinky (
    input  wire       clk,
    input  wire       rst,
    output wire [3:0] led
);
    reg [25:0] count = 0;
    always @(posedge clk)
        if (rst) count <= 0;
        else     count <= count + 1;
    assign led = count[25:22];
endmodule
"""

# Pins from Digilent's Arty A7 master XDC.
ARTY_XDC = """\
set_property -dict { PACKAGE_PIN E3  IOSTANDARD LVCMOS33 } [get_ports clk]
set_property -dict { PACKAGE_PIN C2  IOSTANDARD LVCMOS33 } [get_ports rst]
set_property -dict { PACKAGE_PIN H5  IOSTANDARD LVCMOS33 } [get_ports {led[0]}]
set_property -dict { PACKAGE_PIN J5  IOSTANDARD LVCMOS33 } [get_ports {led[1]}]
set_property -dict { PACKAGE_PIN T9  IOSTANDARD LVCMOS33 } [get_ports {led[2]}]
set_property -dict { PACKAGE_PIN T10 IOSTANDARD LVCMOS33 } [get_ports {led[3]}]
create_clock -period 10.00 [get_ports clk]
"""


class _Registry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


def test_xilinx_flow_produces_a_bitstream(tmp_path):
    reg = _Registry()
    synthesis.register(reg)
    place_route.register(reg)
    src = tmp_path / "blinky.v"
    src.write_text(BLINKY_V)
    xdc = tmp_path / "arty.xdc"
    xdc.write_text(ARTY_XDC)

    # Empty config: no enabled-list restrictions from this machine's ~/.silica.
    with patch("silica.config.load", return_value={}):
        synth = reg.tools["synthesize"](
            top_module="blinky", files=[str(src)], target="xilinx", tool="yosys",
        )
        assert synth["exit_code"] == 0, synth["errors"]

        pnr = reg.tools["run_place_route"](
            netlist=synth["netlist"], arch="xilinx", device=_PART,
            constraint=str(xdc), freq=100.0, tool="nextpnr", timeout=600,
        )
    assert pnr["exit_code"] == 0, pnr["errors"]
    assert not any("FASM" in w["message"] for w in pnr["warnings"]), pnr["warnings"]
    assert pnr["output"].endswith(".bit")
    bitstream = Path(pnr["output"]).read_bytes()
    assert len(bitstream) > 1_000_000
    # The 7-series configuration sync word.
    assert b"\xaa\x99\x55\x66" in bitstream[:1024]
    clocks = pnr["timing_summary"]["clocks"]
    assert clocks and all(c["pass"] for c in clocks), clocks
