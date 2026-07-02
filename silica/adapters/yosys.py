"""Yosys adapter — synthesis and utilization reporting."""

import re
import subprocess
import tempfile

from silica import oss_cad_suite
from silica.adapters._hints import install_hint
from silica.adapters._script_paths import unsafe_script_value

# Abstract FF cells produced by yosys before technology mapping
_FF_CELL_ABSTRACT = {
    "$dff", "$dffe", "$sdff", "$sdffe", "$adff", "$adffe", "$dffsr", "$dffsre",
}
# Tech-mapped single-bit DFF variants (any $_DFF*_ or $_DFFE*_ cell is a FF)
_FF_CELL_MAPPED_RE = re.compile(r"^\$_DFF(E|SR|SRE)?_")
_LUT_CELLS = {
    "$lut", "$pmux",
    "$_LUT1_", "$_LUT2_", "$_LUT3_", "$_LUT4_", "$_LUT5_", "$_LUT6_",
}
_MEM_CELLS = {"$mem", "$mem_v2", "$memrd", "$memrd_v2", "$memwr", "$memwr_v2"}
_DSP_CELLS = {"$mul", "$div", "$mod", "$pow"}

# Abstract cell format:   "  $cell_name    COUNT"  (cell then count, right-aligned)
# Tech-mapped cell format: "    COUNT   $cell_name" (count then cell)
# Both must be matched.
_CELL_RE_ABSTRACT = re.compile(r"^\s+(\$[\w:]+)\s+(\d+)\s*$", re.MULTILINE)
_CELL_RE_MAPPED = re.compile(r"^\s+(\d+)\s+(\$[\w:]+|\w[\w:]*)\s*$", re.MULTILINE)
_WARNING_RE = re.compile(r"^Warning:\s*(.+)$", re.MULTILINE)


def _count_cells(stat_output: str) -> dict:
    luts = ffs = bram = dsp = 0

    def _tally(cell: str, count: int) -> None:
        nonlocal luts, ffs, bram, dsp
        if cell in _FF_CELL_ABSTRACT or _FF_CELL_MAPPED_RE.match(cell):
            ffs += count
        elif cell in _LUT_CELLS:
            luts += count
        elif cell in _MEM_CELLS:
            bram += count
        elif cell in _DSP_CELLS:
            dsp += count

    for m in _CELL_RE_ABSTRACT.finditer(stat_output):
        _tally(m.group(1), int(m.group(2)))
    for m in _CELL_RE_MAPPED.finditer(stat_output):
        _tally(m.group(2), int(m.group(1)))

    return {"luts": luts, "ffs": ffs, "bram": bram, "dsp": dsp,
            "lut_pct": 0.0, "ff_pct": 0.0}


def _parse_warnings(output: str) -> list[dict]:
    warnings = []
    for m in _WARNING_RE.finditer(output):
        warnings.append({
            "file": "",
            "line": 0,
            "severity": "warning",
            "message": m.group(1).strip(),
        })
    return warnings


def run(
    top: str,
    files: list[str],
    target: str = "generic",
    timeout: int = 120,
) -> dict:
    """Synthesize with Yosys and return structured utilization.

    target: "generic" | "ice40" | "ecp5" | "xilinx" | "gowin"
    """
    bad = unsafe_script_value(files, top)
    if bad:
        return {
            "tool": "yosys",
            "target": target,
            "exit_code": -1,
            "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                            "lut_pct": 0.0, "ff_pct": 0.0},
            "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
            "warnings": [],
            "errors": [{"file": "", "line": 0, "severity": "error", "message": bad}],
            "raw_output": "",
        }

    binary = oss_cad_suite.which("yosys")
    if not binary:
        return _not_found()

    read_cmds = []
    for f in files:
        if f.endswith(".sv") or f.endswith(".svh"):
            read_cmds.append(f'read_verilog -sv "{f}"')
        else:
            read_cmds.append(f'read_verilog "{f}"')

    synth_cmd = {
        "generic": f"synth -top {top}",
        "ice40":   f"synth_ice40 -top {top}",
        "ecp5":    f"synth_ecp5 -top {top}",
        "xilinx":  f"synth_xilinx -top {top}",
        "gowin":   f"synth_gowin -top {top}",
    }.get(target, f"synth -top {top}")

    script = "; ".join(read_cmds + [synth_cmd, "stat"])

    with tempfile.TemporaryDirectory(prefix="silica_yosys_") as tmpdir:
        try:
            cp = subprocess.run(
                [binary, "-p", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env=oss_cad_suite.env_with_suite(),
            )
        except subprocess.TimeoutExpired:
            # A hung tool must not crash the MCP server — report it structurally.
            return {
                "tool": "yosys",
                "target": target,
                "exit_code": -1,
                "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                                "lut_pct": 0.0, "ff_pct": 0.0},
                "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
                "warnings": [],
                "errors": [{"file": "", "line": 0, "severity": "error",
                            "message": f"yosys timed out after {timeout}s"}],
                "raw_output": "",
            }

    combined = cp.stdout + cp.stderr
    util = _count_cells(combined)
    warnings = _parse_warnings(combined)

    if cp.returncode != 0:
        error_msg = _extract_error(combined)
        return {
            "tool": "yosys",
            "target": target,
            "exit_code": cp.returncode,
            "utilization": util,
            "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
            "warnings": warnings,
            "errors": [{"file": "", "line": 0, "severity": "error", "message": error_msg}],
            "raw_output": combined,
        }

    return {
        "tool": "yosys",
        "target": target,
        "exit_code": 0,
        "utilization": util,
        # Yosys generic synth has no timing; nextpnr would provide this
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "warnings": warnings,
        "errors": [],
        "raw_output": combined,
    }


def _extract_error(output: str) -> str:
    for line in output.splitlines():
        if line.strip().startswith("ERROR:") or "syntax error" in line.lower():
            return line.strip()
    return "Yosys synthesis failed"


def _not_found() -> dict:
    return {
        "tool": "yosys",
        "target": "unknown",
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": f"yosys not found.\n{install_hint('yosys')}"}],
        "raw_output": "",
    }
