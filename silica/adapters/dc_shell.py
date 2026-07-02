"""DC Shell adapter — Synopsys Design Compiler synthesis."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.adapters._script_paths import unsafe_script_value
from silica.detect import resolve

# DC Shell report_area output
# Number of ports:           12
# Number of cells:           45
# Number of combinational cells:   34
# Number of sequential cells:      11
_AREA_RE = re.compile(r"^(Number of \w[\w ]+):\s*([\d.]+)", re.MULTILINE)
_CELL_AREA_RE = re.compile(r"^Total cell area:\s*([\d.]+)", re.MULTILINE)

# DC Shell message format
# Warning:  message (DC-123)
# Error:    message (DC-456)
_MSG_RE = re.compile(r"^(Error|Warning):\s+(.+?)(?:\s+\(\w+-\d+\))?$", re.MULTILINE)


def _parse_area(output: str) -> dict:
    """Extract rough utilization from DC report_area output."""
    counts: dict[str, int] = {}
    for m in _AREA_RE.finditer(output):
        key = m.group(1).strip().lower()
        val = int(float(m.group(2)))
        counts[key] = val
    return {
        "luts": counts.get("number of combinational cells", 0),
        "ffs": counts.get("number of sequential cells", 0),
        "bram": 0,
        "dsp": 0,
        "lut_pct": 0.0,
        "ff_pct": 0.0,
    }


def _make_tcl(top: str, files: list[str], target: str) -> str:
    read_cmds = "\n".join(
        f"read_file -format sverilog {{{f}}}" for f in files
    )
    tech_line = f"link_library = {{{target}}}" if target not in ("generic", "") else ""
    return f"""\
set_app_var link_library "* {target if target not in ("generic", "") else ""}"
{read_cmds}
analyze -format sverilog {{{" ".join(files)}}}
elaborate {top}
check_design
compile
report_area
report_timing
exit
"""


def run(
    top: str,
    files: list[str],
    target: str = "generic",
    timeout: int = 300,
) -> dict:
    """Synthesize with dc_shell in batch mode.

    target: technology library path, or "generic" for no tech binding.
    """
    bad = unsafe_script_value(files, top, target)
    if bad:
        return _script_error(bad, target)

    binary = resolve("dc_shell")
    if not binary:
        return _not_found(target)

    with tempfile.TemporaryDirectory(prefix="silica_dc_") as tmpdir:
        tcl_path = Path(tmpdir) / "synth.tcl"
        tcl_path.write_text(_make_tcl(top, files, target), encoding="utf-8")

        try:
            cp = subprocess.run(
                [binary, "-f", str(tcl_path), "-no_init"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            # A hung tool must not crash the MCP server — report it structurally.
            return _script_error(f"dc_shell timed out after {timeout}s", target)

    combined = cp.stdout + cp.stderr
    util = _parse_area(combined)

    errors = []
    warnings = []
    for m in _MSG_RE.finditer(combined):
        sev, msg = m.groups()
        entry = {"file": "", "line": 0, "severity": sev.lower(), "message": msg.strip()}
        if sev == "Error":
            errors.append(entry)
        else:
            warnings.append(entry)

    if cp.returncode != 0 and not errors:
        errors.append({"file": "", "line": 0, "severity": "error",
                        "message": f"dc_shell exited with code {cp.returncode}"})

    return {
        "tool": "dc_shell",
        "target": target,
        "exit_code": cp.returncode,
        "utilization": util,
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "warnings": warnings,
        "errors": errors,
        "raw_output": combined,
    }


def _script_error(message: str, target: str) -> dict:
    return {
        "tool": "dc_shell",
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
        "tool": "dc_shell",
        "target": target,
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": "dc_shell not found. Design Compiler requires a Synopsys license."}],
        "raw_output": "",
    }
