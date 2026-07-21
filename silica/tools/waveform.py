"""MCP tools: launch_waveform, read_waveform."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica import oss_cad_suite, vcd
from silica.adapters import verdi as verdi_adapter
from silica.adapters._hints import install_hint
from silica.detect import resolve
from silica.tools._config_dispatch import check_enabled, pick

_OSS_VIEWERS = {"surfer", "gtkwave"}
_ALL_VIEWERS = {"surfer", "gtkwave", "verdi"}

# Discovery mode lists at most this many signals.
_MAX_LISTED_SIGNALS = 1000

# Seconds before giving up on the FST→VCD conversion.
_FST_CONVERT_TIMEOUT = 120


def _fst_to_vcd(fst_path: Path) -> tuple[Path | None, str | None]:
    """Convert an FST trace to a temporary VCD using the bundled fst2vcd.

    FST is GTKWave's compressed binary trace format; rather than decode it in
    Python we shell out to fst2vcd (shipped in the OSS CAD Suite) and reuse the
    VCD parser. Returns (vcd_path, None) on success or (None, error); the
    caller owns the returned temp file and must delete it.
    """
    tool = oss_cad_suite.which("fst2vcd")
    if not tool:
        return None, (
            "Reading .fst needs the fst2vcd converter, which ships with the "
            "OSS CAD Suite but was not found. Install the OSS CAD Suite, or "
            "re-run the simulation with a $dumpfile VCD."
        )
    fd, tmp = tempfile.mkstemp(prefix="silica_fst_", suffix=".vcd")
    os.close(fd)
    try:
        cp = subprocess.run(
            [tool, "-f", str(fst_path), "-o", tmp],
            capture_output=True,
            text=True,
            timeout=_FST_CONVERT_TIMEOUT,
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        os.unlink(tmp)
        return None, f"fst2vcd timed out after {_FST_CONVERT_TIMEOUT}s"
    if cp.returncode != 0:
        os.unlink(tmp)
        detail = (cp.stderr or cp.stdout).strip()
        return None, f"fst2vcd could not convert {fst_path.name}: {detail}"
    return Path(tmp), None


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
        """Read signal values from a VCD or FST trace — no viewer needed.

        Typical debug flow:
            1. result = run_simulation(..., trace=True)   # note failure time T
            2. read_waveform(result["trace_vcd"])          # discover signal names
            3. read_waveform(result["trace_vcd"],
                             signals=["dut.state", "dut.count"],
                             time_start=T-100, time_end=T+10)

        Args:
            trace_file: Path to the trace. VCD is read directly; .fst is
                        converted via the OSS CAD Suite's fst2vcd first.
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

        suffix = path.suffix.lower()
        if suffix == ".fsdb":
            return {"error": (
                "FSDB is a proprietary Synopsys format; read_waveform cannot "
                "parse it. Re-run the simulation with a $dumpfile VCD, or use "
                "launch_waveform with the verdi viewer."
            )}

        # FST is binary — convert to a throwaway VCD, then parse as usual.
        tmp_vcd: Path | None = None
        if suffix == ".fst":
            tmp_vcd, err = _fst_to_vcd(path)
            if err:
                return {"error": err}
            parse_target = tmp_vcd
        else:
            parse_target = path

        try:
            parsed = vcd.parse(
                str(parse_target),
                signals=signals,
                time_start=time_start,
                time_end=time_end,
                max_transitions=max_transitions,
            )
        except (ValueError, OSError) as exc:
            return {"error": f"Failed to parse VCD: {exc}"}
        finally:
            if tmp_vcd is not None:
                try:
                    os.unlink(tmp_vcd)
                except OSError:
                    pass

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
