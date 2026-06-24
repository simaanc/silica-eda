"""MCP tool: synthesize."""

import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import yosys


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def synthesize(
        top_module: str,
        files: list[str],
        target: str = "generic",
        tool: str = "auto",
        timeout: int = 120,
    ) -> dict:
        """Synthesize RTL and return structured utilization and timing summary.

        Args:
            top_module: Name of the top-level module to synthesize.
            files: List of source file paths (.sv / .v).
            target: Synthesis target — "generic" | "ice40" | "ecp5" | "xilinx" | "gowin".
            tool: "auto" | "yosys". Auto priority: yosys → (commercial tools post-MVP).
            timeout: Seconds before killing the synthesis process.

        Returns a SynthesisResult dict:
            tool, target, exit_code, utilization {luts, ffs, bram, dsp, lut_pct, ff_pct},
            timing_summary {wns, tns, failing_endpoints}, warnings, errors, raw_output
        """
        if tool == "auto":
            tool = "yosys" if shutil.which("yosys") else "none"

        if tool == "yosys":
            return yosys.run(top_module, files, target=target, timeout=timeout)
        else:
            return {
                "tool": "none",
                "target": target,
                "exit_code": -1,
                "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                                "lut_pct": 0.0, "ff_pct": 0.0},
                "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
                "warnings": [],
                "errors": [{
                    "file": "",
                    "line": 0,
                    "severity": "error",
                    "message": "No synthesis tool found. Install Yosys: brew install yosys",
                }],
                "raw_output": "",
            }
