"""MCP tool: launch_waveform."""

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters._hints import install_hint
from silica.tools._config_dispatch import pick

_VIEWERS = {"surfer", "gtkwave"}


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def launch_waveform(trace_file: str, viewer: str = "auto") -> dict:
        """Open a VCD/FST trace file in a waveform viewer (fire-and-forget).

        Typical flow:
            1. result = run_simulation(..., trace=True)
            2. launch_waveform(result["trace_vcd"])

        Args:
            trace_file: Absolute path to the .vcd or .fst trace file.
            viewer: "auto" | "surfer" | "gtkwave". Auto picks from config priority.

        Returns:
            {"viewer": str, "launched": bool, "trace": str}
            or {"launched": False, "error": str} on failure.
        """
        if viewer == "auto":
            chosen = pick("waveform")
            if chosen in _VIEWERS:
                viewer = chosen
            else:
                return {
                    "launched": False,
                    "error": (
                        "No waveform viewer found. Install Surfer or GTKWave:\n"
                        f"Surfer:   {install_hint('surfer')}\n"
                        f"GTKWave: {install_hint('gtkwave')}"
                    ),
                }

        binary = shutil.which(viewer)
        if not binary:
            return {
                "launched": False,
                "error": f"{viewer} not found on PATH.\n{install_hint(viewer)}",
            }

        subprocess.Popen([binary, trace_file])
        return {
            "viewer": viewer,
            "launched": True,
            "trace": trace_file,
        }
