"""MCP tools: launch_waveform, read_waveform."""

import atexit
import os
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
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

# --- FST→VCD conversion cache ------------------------------------------------
# fst2vcd decodes the *whole* trace, so the usual debug pattern — one discovery
# read to list signals, then several windowed reads of the same trace — would
# otherwise reconvert it on every call. Cache the converted VCD per trace path,
# keyed by the FST's (mtime_ns, size) so a rerun that overwrites the trace
# invalidates the stale VCD. The cache is bounded (LRU) and its files live in a
# single temp dir removed at process exit.
_MAX_FST_CACHE = 8
# resolved FST path -> ((mtime_ns, size), converted VCD path)
_fst_cache: "OrderedDict[str, tuple[tuple[int, int], Path]]" = OrderedDict()
_fst_cache_dir: str | None = None
# Tool calls can run concurrently on worker threads, and a call can evict the
# VCD another call is about to parse. Hold this across convert *and* parse.
_fst_lock = threading.Lock()


def _cache_dir() -> str:
    """Lazily create the shared cache dir, cleaned up at interpreter exit."""
    global _fst_cache_dir
    if _fst_cache_dir is None:
        _fst_cache_dir = tempfile.mkdtemp(prefix="silica_fst_cache_")
        atexit.register(shutil.rmtree, _fst_cache_dir, True)
    return _fst_cache_dir


def _drop_fst_cache_entry(key: str) -> None:
    entry = _fst_cache.pop(key, None)
    if entry is not None:
        try:
            entry[1].unlink()
        except OSError:
            pass


def _evict_fst_cache() -> None:
    while len(_fst_cache) > _MAX_FST_CACHE:
        _, (_, vcd_path) = _fst_cache.popitem(last=False)
        try:
            vcd_path.unlink()
        except OSError:
            pass


def _fst_to_vcd(fst_path: Path) -> tuple[Path | None, str | None]:
    """Convert an FST trace to a VCD (cached) using the bundled fst2vcd.

    FST is GTKWave's compressed binary trace format; rather than decode it in
    Python we shell out to fst2vcd (shipped in the OSS CAD Suite) and reuse the
    VCD parser. The converted VCD is cached per trace path and reused until the
    FST changes on disk, so repeated reads of one trace convert it only once.
    Returns (vcd_path, None) on success or (None, error); the returned path is
    owned by the module cache and must NOT be deleted by the caller.
    """
    key = str(fst_path.resolve())
    try:
        st = fst_path.stat()
    except OSError as exc:
        return None, f"Cannot read {fst_path.name}: {exc}"
    stamp = (st.st_mtime_ns, st.st_size)

    cached = _fst_cache.get(key)
    if cached is not None:
        cached_stamp, cached_vcd = cached
        if cached_stamp == stamp and cached_vcd.is_file():
            _fst_cache.move_to_end(key)  # mark most-recently-used
            return cached_vcd, None
        # Trace changed on disk (or the VCD vanished) — reconvert.
        _drop_fst_cache_entry(key)

    tool = oss_cad_suite.which("fst2vcd")
    if not tool:
        return None, (
            "Reading .fst needs the fst2vcd converter, which ships with the "
            "OSS CAD Suite but was not found. Install the OSS CAD Suite, or "
            "re-run the simulation with a $dumpfile VCD."
        )
    fd, tmp = tempfile.mkstemp(prefix="silica_fst_", suffix=".vcd", dir=_cache_dir())
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

    vcd_path = Path(tmp)
    _fst_cache[key] = (stamp, vcd_path)
    _fst_cache.move_to_end(key)
    _evict_fst_cache()
    return vcd_path, None


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

        def parse(target: Path) -> tuple[dict | None, str | None]:
            try:
                return vcd.parse(
                    str(target),
                    signals=signals,
                    time_start=time_start,
                    time_end=time_end,
                    max_transitions=max_transitions,
                ), None
            except (ValueError, OSError) as exc:
                return None, f"Failed to parse VCD: {exc}"

        # FST is binary — convert to a VCD (cached per trace), then parse as
        # usual. The VCD is owned by the cache, so we must not delete it here.
        if suffix == ".fst":
            with _fst_lock:
                vcd_path, err = _fst_to_vcd(path)
                if not err:
                    parsed, err = parse(vcd_path)
        else:
            parsed, err = parse(path)
        if err:
            return {"error": err}

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
