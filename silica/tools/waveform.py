"""MCP tools: launch_waveform, read_waveform."""

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica import vcd
from silica.adapters import verdi as verdi_adapter
from silica.adapters._hints import install_hint
from silica.detect import resolve
from silica.tools._config_dispatch import check_enabled, pick

_OSS_VIEWERS = {"surfer", "gtkwave"}
_ALL_VIEWERS = {"surfer", "gtkwave", "verdi"}

# Discovery mode lists at most this many signals.
_MAX_LISTED_SIGNALS = 1000


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

    @mcp.tool()
    def read_waveform(
        trace_file: str,
        signals: list[str] | None = None,
        time_start: int | None = None,
        time_end: int | None = None,
        max_transitions: int = 200,
    ) -> dict:
        """Read signal values from a VCD trace — no waveform viewer needed.

        Typical debug flow:
            1. result = run_simulation(..., trace=True)   # note failure time T
            2. read_waveform(result["trace_vcd"])          # discover signal names
            3. read_waveform(result["trace_vcd"],
                             signals=["dut.state", "dut.count"],
                             time_start=T-100, time_end=T+10)

        Args:
            trace_file: Path to the .vcd trace (from run_simulation's trace_vcd).
            signals: Signal names to read. A name matches on the full
                     hierarchical path ("tb.dut.count") or any trailing
                     component ("count", "dut.count"). Omit to list the
                     signals available in the trace instead.
            time_start: Window start in VCD ticks (multiply timescale to get
                        time). Each signal's value just before the window is
                        included so state at window start is known.
            time_end: Window end in VCD ticks.
            max_transitions: Per-signal cap; "truncated" is set when hit.

        Returns:
            Discovery mode: {trace, timescale, end_time, signal_count,
                             signals [{name, width}]}
            With signals:   {trace, timescale, end_time,
                             signals [{name, width,
                                       transitions [{time, value}],
                                       truncated}],
                             not_found}
            {"error": str} on failure. Values are bit strings ("0101",
            may contain x/z); times are VCD ticks.
        """
        path = Path(trace_file)
        if not path.is_file():
            return {"error": f"Trace file not found: {trace_file}"}
        if path.suffix.lower() in (".fst", ".fsdb"):
            return {"error": (
                f"Only VCD traces can be read directly; {path.suffix} is a "
                "binary format. Re-run the simulation with a $dumpfile VCD, "
                "or use launch_waveform for a viewer."
            )}

        try:
            parsed = vcd.parse(
                str(path),
                signals=signals,
                time_start=time_start,
                time_end=time_end,
                max_transitions=max_transitions,
            )
        except (ValueError, OSError) as exc:
            return {"error": f"Failed to parse VCD: {exc}"}

        if not signals:
            available = parsed["all_signals"]
            return {
                "trace": trace_file,
                "timescale": parsed["timescale"],
                "end_time": parsed["end_time"],
                "signal_count": len(available),
                "signals": available[:_MAX_LISTED_SIGNALS],
            }

        result = {
            "trace": trace_file,
            "timescale": parsed["timescale"],
            "end_time": parsed["end_time"],
            "signals": parsed["signals"],
            "not_found": parsed["not_found"],
        }
        if parsed["not_found"]:
            # Nudge toward valid names without re-listing on every call.
            result["hint"] = (
                "Call read_waveform without 'signals' to list the names "
                "available in this trace."
            )
        return result
