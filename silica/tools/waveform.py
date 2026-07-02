"""MCP tool: launch_waveform."""

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import verdi as verdi_adapter
from silica.adapters._hints import install_hint
from silica.detect import resolve
from silica.tools._config_dispatch import check_enabled, pick

_OSS_VIEWERS = {"surfer", "gtkwave"}
_ALL_VIEWERS = {"surfer", "gtkwave", "verdi"}


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def launch_waveform(trace_file: str, viewer: str = "auto") -> dict:
        """Open a VCD/FST/FSDB trace file in a waveform viewer (fire-and-forget).

        Typical flow:
            1. result = run_simulation(..., trace=True)
            2. launch_waveform(result["trace_vcd"])

        Args:
            trace_file: Absolute path to the .vcd, .fst, or .fsdb trace file.
            viewer: "auto" | "surfer" | "gtkwave" | "verdi".
                    Auto picks from config priority order.

        Returns:
            {"viewer": str, "launched": bool, "trace": str}
            or {"launched": False, "error": str} on failure.
        """
        if viewer == "auto":
            chosen = pick("waveform")
            if chosen in _ALL_VIEWERS:
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
        else:
            # Explicit override — respect the user's configured enabled list.
            disabled = check_enabled("waveform", viewer)
            if disabled:
                return {"launched": False, "error": disabled}

        if viewer == "verdi":
            return verdi_adapter.launch(trace_file)

        # Deliberate asymmetry: surfer/gtkwave have no adapter modules.
        # Launching them is a one-line fire-and-forget Popen with no output
        # to parse, so an adapter would only add indirection. verdi goes
        # through an adapter because it needs license/env handling.
        # OSS viewers — look up via resolve() so OSS CAD Suite path is checked
        binary = resolve(viewer) or shutil.which(viewer)
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
