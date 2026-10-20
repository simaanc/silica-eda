"""MCP tool: run_place_route."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import nextpnr
from silica.tools._config_dispatch import check_enabled, pick


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def run_place_route(
        netlist: str,
        arch: str = "ice40",
        device: str = "hx8k",
        package: str | None = None,
        constraint: str | None = None,
        output: str | None = None,
        freq: float | None = None,
        tool: str = "auto",
        timeout: int = 120,
    ) -> dict:
        """Place and route an FPGA netlist and return timing and utilization.

        Takes a Yosys JSON netlist (from synthesize with target "ice40"/"ecp5"/
        "xilinx"/etc.). The output is a bitstream ready for program_device
        when the packing tool is available: a .bit for xilinx (openXC7's
        fpga-as), a .bin for ice40 (icepack) and a .bit for ecp5 (ecppack).
        Without it, the output is nextpnr's FASM or text config (.asc /
        .textcfg) and a warning says what is missing.

        Args:
            netlist: Path to Yosys JSON netlist (produced by the synthesize tool).
            arch: FPGA architecture — "ice40" | "ecp5" | "nexus" | "machxo2" |
                  "generic" | "xilinx".
            device: Device variant within the architecture:
                    ice40: "hx1k" | "hx4k" | "hx8k" | "up5k" | "lp1k" | "lp8k" | ...
                    ecp5:  "LFE5U-12F" | "LFE5U-25F" | "LFE5U-45F" | "LFE5U-85F",
                           also LFE5UM-/LFE5UM5G- parts; a speed grade suffix
                           (e.g. "LFE5U-25F-6") sets --speed.
                    xilinx: full 7-series part with speed grade, e.g.
                            "xc7a100tcsg324-1" (Arty A7-100T). Uses openXC7's
                            nextpnr-xilinx; its chip database is found through
                            NEXTPNR_XILINX_CHIPDB_DIR or <FAMILY>_CHIPDB, and
                            the FASM is assembled into a .bit with fpga-as when
                            PRJXRAY_DB_DIR is set. A chip database path also
                            works as device (the result is then FASM).
            package: Package code, e.g. "ct256" (ice40), "CABGA381" (ecp5). Optional.
            constraint: Path to physical constraint file (.pcf for ice40, .lpf for ecp5,
                        .xdc for xilinx).
            output: Output file path for the bitstream. Auto-placed in temp dir
                    if omitted — the path is returned in the result. A path
                    ending in .asc/.textcfg/.fasm keeps nextpnr's file there
                    and writes the bitstream beside it.
            freq: Target clock frequency in MHz for timing checks.
            tool: "auto" | "nextpnr". Auto uses config priority order.
            timeout: Seconds before killing the tool.

        Returns a PlaceRouteResult dict:
            tool, target, exit_code,
            timing_summary {clocks [{clock, max_freq_mhz, pass}], wns, failing_endpoints},
            utilization {<cell_type>: {used, total, pct}},
            output (path to the bitstream, or to nextpnr's file if it
                    couldn't be packed),
            workdir, warnings, errors, raw_output
        """
        if tool == "auto":
            chosen = pick("place_route")
            tool = chosen or "nextpnr"
        else:
            # Explicit override — respect the user's configured enabled list.
            disabled = check_enabled("place_route", tool)
            if disabled:
                return {
                    "tool": tool,
                    "target": device,
                    "exit_code": -1,
                    "timing_summary": {"clocks": [], "wns": 0.0, "failing_endpoints": 0},
                    "utilization": {},
                    "output": None,
                    "workdir": "",
                    "warnings": [],
                    "errors": [{"message": disabled}],
                    "raw_output": "",
                }

        if tool == "nextpnr":
            return nextpnr.run(
                netlist=netlist,
                arch=arch,
                device=device,
                package=package,
                constraint=constraint,
                output=output,
                freq=freq,
                timeout=timeout,
            )

        return {
            "tool": "none",
            "target": device,
            "exit_code": -1,
            "timing_summary": {"clocks": [], "wns": 0.0, "failing_endpoints": 0},
            "utilization": {},
            "output": None,
            "workdir": "",
            "warnings": [],
            "errors": [{"message": f"Unknown place-and-route tool '{tool}'. "
                                   "Supported: auto, nextpnr."}],
            "raw_output": "",
        }
