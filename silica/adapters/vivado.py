"""Vivado adapter — AMD/Xilinx Vivado synthesis."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.adapters._script_paths import unsafe_script_value
from silica.detect import resolve

# Vivado utilization report patterns
# | Slice LUTs*              |   1234 |     0 |    20800 |   5.93 |
_UTIL_RE = re.compile(
    r"\|\s*(?P<resource>Slice LUTs\*?|Slice Registers|DSPs|Block RAM Tile)\s*\|\s*(?P<used>\d+)",
    re.IGNORECASE,
)

# Timing: WNS(ns)  TNS(ns)  TNS Failing Endpoints
_TIMING_RE = re.compile(
    r"WNS\(ns\).*?\n[-\s]+\n\s*(?P<wns>-?\d+\.\d+)\s+(?P<tns>-?\d+\.\d+)\s+(?P<fail>\d+)",
    re.DOTALL,
)

_CRITICAL_RE = re.compile(r"^CRITICAL WARNING:\s*(.+)$", re.MULTILINE)
_ERROR_RE = re.compile(r"^ERROR:\s*(.+)$", re.MULTILINE)


def _parse_utilization(output: str) -> dict:
    util = {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0}
    for m in _UTIL_RE.finditer(output):
        res = m.group("resource").lower()
        val = int(m.group("used"))
        if "lut" in res:
            util["luts"] = val
        elif "register" in res:
            util["ffs"] = val
        elif "dsp" in res:
            util["dsp"] = val
        elif "block ram" in res or "bram" in res:
            util["bram"] = val
    return util


def _parse_timing(output: str) -> dict:
    m = _TIMING_RE.search(output)
    if m:
        return {
            "wns": float(m.group("wns")),
            "tns": float(m.group("tns")),
            "failing_endpoints": int(m.group("fail")),
        }
    return {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0}


def _make_tcl(top: str, files: list[str], part: str) -> str:
    read_cmds = "\n".join(
        f"read_verilog -sv {{{f}}}" if f.endswith((".sv", ".svh")) else f"read_verilog {{{f}}}"
        for f in files
    )
    return f"""\
{read_cmds}
synth_design -top {top} -part {part}
report_utilization
report_timing_summary -max_paths 10
exit
"""


def run(
    top: str,
    files: list[str],
    target: str = "generic",
    timeout: int = 300,
) -> dict:
    """Synthesize with Vivado in batch mode.

    target: FPGA part string e.g. "xc7a35tcsg324-1" (default) or
            shorthand "artix7" / "ultrascale" / "ultrascale+".
    """
    part_map = {
        "generic":     "xc7a35tcsg324-1",
        "artix7":      "xc7a35tcsg324-1",
        "kintex7":     "xc7k70tfbg484-1",
        "virtex7":     "xc7v585tffg1157-1",
        "ultrascale":  "xcku040-fbva676-1-c",
        "ultrascale+": "xcku5p-sfvb784-1-e",
        "zynq":        "xc7z020clg484-1",
    }
    part = part_map.get(target, target)

    bad = unsafe_script_value(files, top, part)
    if bad:
        return _script_error(bad, part)

    binary = resolve("vivado")
    if not binary:
        return _not_found(target)

    with tempfile.TemporaryDirectory(prefix="silica_vivado_") as tmpdir:
        tcl_path = Path(tmpdir) / "synth.tcl"
        tcl_path.write_text(_make_tcl(top, files, part), encoding="utf-8")

        cp = subprocess.run(
            [binary, "-mode", "batch", "-source", str(tcl_path),
             "-nojournal", "-nolog"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
        )

    combined = cp.stdout + cp.stderr
    util = _parse_utilization(combined)
    timing = _parse_timing(combined)

    errors = [
        {"file": "", "line": 0, "severity": "error", "message": m.group(1).strip()}
        for m in _ERROR_RE.finditer(combined)
    ]
    warnings = [
        {"file": "", "line": 0, "severity": "warning", "message": m.group(1).strip()}
        for m in _CRITICAL_RE.finditer(combined)
    ]

    if cp.returncode != 0 and not errors:
        errors.append({"file": "", "line": 0, "severity": "error",
                        "message": f"Vivado exited with code {cp.returncode}"})

    # rc==0 with nothing parsed is indistinguishable from an empty design;
    # flag it so all-zero metrics aren't read as a real result.
    if cp.returncode == 0 and not any(util.values()) and _TIMING_RE.search(combined) is None:
        warnings.append({"file": "", "line": 0, "severity": "warning", "message": (
            "No utilization or timing figures found in Vivado output; "
            "the report format may be unsupported — check raw_output."
        )})

    return {
        "tool": "vivado",
        "target": part,
        "exit_code": cp.returncode,
        "utilization": util,
        "timing_summary": timing,
        "warnings": warnings,
        "errors": errors,
        "raw_output": combined,
    }


def _script_error(message: str, target: str) -> dict:
    return {
        "tool": "vivado",
        "target": target,
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error", "message": message}],
        "raw_output": "",
    }


def _not_found(target: str = "generic") -> dict:
    return {
        "tool": "vivado",
        "target": target,
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": "vivado not found. Vivado requires an AMD/Xilinx installation."}],
        "raw_output": "",
    }
