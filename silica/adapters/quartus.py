"""Quartus adapter — Intel/Altera Quartus Prime synthesis."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.adapters._script_paths import unsafe_script_value
from silica.detect import resolve

# Quartus report parser — resource utilization from map/fit reports
# Total logic elements            : 1234 / 39,600 ( 3 % )
_LOGIC_RE = re.compile(r"Total logic elements\s*:\s*([\d,]+)", re.IGNORECASE)
_FF_RE = re.compile(r"Total registers\s*:\s*([\d,]+)", re.IGNORECASE)
_DSP_RE = re.compile(r"Total DSP elements\s*:\s*([\d,]+)", re.IGNORECASE)
_MEM_RE = re.compile(r"Total memory bits\s*:\s*([\d,]+)", re.IGNORECASE)

# Quartus message format: Warning (10264): ...  or  Error (10030): ...
_MSG_RE = re.compile(r"^(Error|Warning)\s*\([\d]+\):\s*(.+)$", re.MULTILINE)


def _int_from_match(m: re.Match | None) -> int:
    if not m:
        return 0
    return int(m.group(1).replace(",", ""))


def _parse_report(text: str) -> dict:
    return {
        "luts": _int_from_match(_LOGIC_RE.search(text)),
        "ffs": _int_from_match(_FF_RE.search(text)),
        "bram": _int_from_match(_MEM_RE.search(text)),
        "dsp": _int_from_match(_DSP_RE.search(text)),
        "lut_pct": 0.0,
        "ff_pct": 0.0,
    }


def _make_qsf(top: str, files: list[str], device: str) -> str:
    file_lines = "\n".join(
        f'set_global_assignment -name '
        f'{"SYSTEMVERILOG_FILE" if f.endswith((".sv", ".svh")) else "VERILOG_FILE"} "{f}"'
        for f in files
    )
    return f"""\
set_global_assignment -name FAMILY "{device}"
set_global_assignment -name TOP_LEVEL_ENTITY {top}
{file_lines}
"""


_DEVICE_MAP = {
    "generic":    "Cyclone V",
    "cyclone5":   "Cyclone V",
    "cyclone10":  "Cyclone 10 LP",
    "arria10":    "Arria 10",
    "stratix10":  "Stratix 10",
    "agilex":     "Agilex 7",
}


def run(
    top: str,
    files: list[str],
    target: str = "generic",
    timeout: int = 300,
) -> dict:
    """Synthesize with Quartus Prime (quartus_map) in batch mode.

    target: device family string e.g. "cyclone5", "arria10", "stratix10".
    """
    device = _DEVICE_MAP.get(target, target)

    bad = unsafe_script_value(files, top, device)
    if bad:
        return _script_error(bad, device)

    binary = resolve("quartus")  # resolves quartus_sh
    if not binary:
        return _not_found(target)

    # Prefer quartus_map for synthesis-only; fall back to quartus_sh --flow
    quartus_dir = Path(binary).parent
    quartus_map = str(quartus_dir / "quartus_map")
    if not Path(quartus_map).exists():
        quartus_map = "quartus_map"

    with tempfile.TemporaryDirectory(prefix="silica_quartus_") as tmpdir:
        qsf_path = Path(tmpdir) / f"{top}.qsf"
        qsf_path.write_text(_make_qsf(top, files, device), encoding="utf-8")

        try:
            cp = subprocess.run(
                [quartus_map,
                 "--read_settings_files=on",
                 "--write_settings_files=off",
                 top,
                 f"--settings={qsf_path}"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            # A hung tool must not crash the MCP server — report it structurally.
            return _script_error(f"quartus_map timed out after {timeout}s", device)

    combined = cp.stdout + cp.stderr
    util = _parse_report(combined)

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
                        "message": f"quartus_map exited with code {cp.returncode}"})

    # rc==0 with nothing parsed is indistinguishable from an empty design;
    # flag it so all-zero metrics aren't read as a real result.
    if cp.returncode == 0 and not any(util.values()):
        warnings.append({"file": "", "line": 0, "severity": "warning", "message": (
            "No utilization figures found in Quartus output; "
            "the report format may be unsupported — check raw_output."
        )})

    return {
        "tool": "quartus",
        "target": device,
        "exit_code": cp.returncode,
        "utilization": util,
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "netlist": None,
        "warnings": warnings,
        "errors": errors,
        "raw_output": combined,
    }


def _script_error(message: str, target: str) -> dict:
    return {
        "tool": "quartus",
        "target": target,
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "netlist": None,
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error", "message": message}],
        "raw_output": "",
    }


def _not_found(target: str = "generic") -> dict:
    return {
        "tool": "quartus",
        "target": target,
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "netlist": None,
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": ("quartus_sh/quartus_map not found. "
                                "Quartus requires an Intel installation.")}],
        "raw_output": "",
    }
