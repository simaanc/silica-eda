"""MCP tool: run_place_route."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import nextpnr
from silica.tools._config_dispatch import check_enabled, pick


def register(mcp: "FastMCP") -> None:
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

        Takes a Yosys JSON netlist (from synthesize with target "ice40"/"ecp5"/etc.)
        and produces a bitstream/config file ready for programming.

        Args:
            netlist: Path to Yosys JSON netlist (produced by the synthesize tool).
            arch: FPGA architecture — "ice40" | "ecp5" | "nexus" | "machxo2" | "generic".
            device: Device variant within the architecture:
                    ice40: "hx1k" | "hx4k" | "hx8k" | "up5k" | "lp1k" | "lp8k" | ...
                    ecp5:  "LFE5U-12F" | "LFE5U-25F" | "LFE5U-45F" | "LFE5U-85F"
            package: Package code, e.g. "ct256" (ice40), "CABGA381" (ecp5). Optional.
            constraint: Path to physical constraint file (.pcf for ice40, .lpf for ecp5).
            output: Output file path for the bitstream/config. Auto-placed in temp dir
                    if omitted — the path is returned in the result.
            freq: Target clock frequency in MHz for timing checks.
            tool: "auto" | "nextpnr". Auto uses config priority order.
            timeout: Seconds before killing the tool.

        Returns a PlaceRouteResult dict:
            tool, target, exit_code,
            timing_summary {clocks [{clock, max_freq_mhz, pass}], wns, failing_endpoints},
            utilization {<cell_type>: {used, total, pct}},
            output (path to bitstream/config file — pass to program_device),
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
