"""Yosys adapter — synthesis and utilization reporting."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from silica import oss_cad_suite
from silica.adapters._hints import install_hint
from silica.adapters._script_paths import unsafe_script_value

# Abstract FF cells produced by yosys before technology mapping
_FF_CELL_ABSTRACT = {
    "$dff", "$dffe", "$sdff", "$sdffe", "$adff", "$adffe", "$dffsr", "$dffsre",
}
# Single-bit FF cells: yosys gate-level ($_DFF*_, $_SDFF*_, ...) and the
# primitives synth_<arch> maps to (ice40 SB_DFF*, ecp5 TRELLIS_FF, gowin DFF*,
# xilinx FD[CPRS]E).
_FF_CELL_MAPPED_RE = re.compile(
    r"^(\$_(SDFF|ALDFF|DFF)\w*_|SB_DFF\w*|TRELLIS_FF|DFF[A-Z]*|FD[CPRS]E(_1)?)$"
)
_LUT_CELLS = {
    "$lut", "$pmux",
    "$_LUT1_", "$_LUT2_", "$_LUT3_", "$_LUT4_", "$_LUT5_", "$_LUT6_",
}
# ice40 SB_LUT4; ecp5 LUT4; gowin LUT1-4; xilinx LUT1-6
_LUT_CELL_MAPPED_RE = re.compile(r"^(SB_LUT4|LUT[1-6])$")
_MEM_CELLS = {"$mem", "$mem_v2", "$memrd", "$memrd_v2", "$memwr", "$memwr_v2"}
_MEM_CELL_MAPPED_RE = re.compile(
    r"^(SB_RAM40_4K\w*|DP16KD|PDPW16KD|SPX?9?|DPX?9?B?|SDPX?9?B?|pROMX?9?|RAMB(18|36)E[12])$"
)
_DSP_CELLS = {"$mul", "$div", "$mod", "$pow"}
_DSP_CELL_MAPPED_RE = re.compile(
    r"^(SB_MAC16|MULT18X18D|ALU54D|MULT(9X9|18X18|36X36)|MULTALU\w+|MULTADDALU\w+|DSP48E[12])$"
)

# Abstract cell format:   "  $cell_name    COUNT"  (cell then count, right-aligned)
# Tech-mapped cell format: "    COUNT   $cell_name" (count then cell)
# Both must be matched.
_CELL_RE_ABSTRACT = re.compile(r"^\s+(\$[\w:]+)\s+(\d+)\s*$", re.MULTILINE)
_CELL_RE_MAPPED = re.compile(r"^\s+(\d+)\s+(\$[\w:]+|\w[\w:]*)\s*$", re.MULTILINE)
# Yosys diagnostics, located two ways (or not at all):
#   rom.v:4: ERROR:Can not open file `nope.hex` for \$readmemh.     (prefix)
#   range.v:3: Warning: Range select out of bounds on signal `\w': ...
#   Warning: reg '\y' is assigned in a continuous assignment at t.sv:5.10-5.15.
#   ERROR: Module `\sub' referenced in module `\t' ... is not part of the design.
_DIAG_RE = re.compile(
    r"^(?:(?P<file>(?:[A-Za-z]:)?[^:\s][^:\n]*):(?P<line>\d+):[ \t]*)?"
    r"(?P<sev>ERROR|Warning):[ \t]*(?P<msg>.+)$",
    re.MULTILINE,
)
# "at file:line" or "at file:line.col-line.col" inside the message. Only HDL
# files count: cell names such as $auto$blifparse.cc:396:... look the same.
_AT_LOC_RE = re.compile(
    r"\bat ((?:[A-Za-z]:)?[^\s:]+\.(?:sv|svh|v|vh|vhd|vhdl)):(\d+)(?:\.\d+(?:-\d+\.\d+)?)?"
)

# Targets whose synth_<arch> command supports -json and whose netlist
# nextpnr (or a vendor P&R flow) can consume.
_FPGA_TARGETS = {"ice40", "ecp5", "xilinx", "gowin"}


def _final_stat(output: str) -> str:
    """Return the design-wide cell counts from the last ``stat`` report.

    synth_<arch> prints its own statistics before the script's ``stat`` runs,
    and each report lists every module and then the hierarchy total, so
    counting every block counts each cell several times over."""
    start = output.rfind("Printing statistics.")
    report = output[start:] if start >= 0 else output
    total = report.find("=== design hierarchy ===")
    return report[total:] if total >= 0 else report


def _count_cells(stat_output: str) -> dict:
    stat_output = _final_stat(stat_output)
    luts = ffs = bram = dsp = 0

    def _tally(cell: str, count: int) -> None:
        nonlocal luts, ffs, bram, dsp
        if cell in _FF_CELL_ABSTRACT or _FF_CELL_MAPPED_RE.match(cell):
            ffs += count
        elif cell in _LUT_CELLS or _LUT_CELL_MAPPED_RE.match(cell):
            luts += count
        elif cell in _MEM_CELLS or _MEM_CELL_MAPPED_RE.match(cell):
            bram += count
        elif cell in _DSP_CELLS or _DSP_CELL_MAPPED_RE.match(cell):
            dsp += count

    for m in _CELL_RE_ABSTRACT.finditer(stat_output):
        _tally(m.group(1), int(m.group(2)))
    for m in _CELL_RE_MAPPED.finditer(stat_output):
        _tally(m.group(2), int(m.group(1)))

    return {"luts": luts, "ffs": ffs, "bram": bram, "dsp": dsp,
            "lut_pct": 0.0, "ff_pct": 0.0}


def _diagnostic(m: re.Match, severity: str) -> dict:
    """Build a diagnostic dict, taking the location from the prefix or an "at" clause.

    A message with neither keeps file "" and line 0."""
    message = m.group("msg").strip()
    file, line = m.group("file"), m.group("line")
    if not file:
        at = None
        for at in _AT_LOC_RE.finditer(message):
            pass  # the last "at" clause is the one the message ends with
        if at:
            file, line = at.group(1), at.group(2)
    return {
        "file": (file or "").strip(),
        "line": int(line) if line else 0,
        "severity": severity,
        "message": message,
    }


def _parse_warnings(output: str) -> list[dict]:
    return [_diagnostic(m, "warning") for m in _DIAG_RE.finditer(output)
            if m.group("sev") == "Warning"]


def run(
    top: str,
    files: list[str],
    target: str = "generic",
    timeout: int = 120,
) -> dict:
    """Synthesize with Yosys and return structured utilization.

    target: "generic" | "ice40" | "ecp5" | "xilinx" | "gowin"

    For FPGA targets a JSON netlist is written and its path returned under
    "netlist" — pass it to run_place_route. "netlist" is None for the
    generic target and on any failure.
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
            "netlist": None,
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

    # FPGA netlist is written to a fixed name inside the run's cwd, so no
    # user-controlled value reaches the script — the injection guard above
    # only had to vet files/top.
    if target in _FPGA_TARGETS:
        synth_cmd += " -json netlist.json"

    script = "; ".join(read_cmds + [synth_cmd, "stat"])

    netlist_out = None
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
                "netlist": None,
                "warnings": [],
                "errors": [{"file": "", "line": 0, "severity": "error",
                            "message": f"yosys timed out after {timeout}s"}],
                "raw_output": "",
            }

        tmp_netlist = Path(tmpdir) / "netlist.json"
        if cp.returncode == 0 and tmp_netlist.exists():
            # Persistent dir only after success — mkdtemp, never
            # TemporaryDirectory (it would auto-delete under the caller).
            outdir = tempfile.mkdtemp(prefix="silica_synth_")
            netlist_out = str(Path(outdir) / "netlist.json")
            shutil.move(str(tmp_netlist), netlist_out)

    combined = cp.stdout + cp.stderr
    util = _count_cells(combined)
    warnings = _parse_warnings(combined)

    if cp.returncode != 0:
        error = _extract_error(combined)
        return {
            "tool": "yosys",
            "target": target,
            "exit_code": cp.returncode,
            "utilization": util,
            "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
            "netlist": None,
            "warnings": warnings,
            "errors": [error],
            "raw_output": combined,
        }

    return {
        "tool": "yosys",
        "target": target,
        "exit_code": 0,
        "utilization": util,
        # Yosys generic synth has no timing; nextpnr would provide this
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "netlist": netlist_out,
        "warnings": warnings,
        "errors": [],
        "raw_output": combined,
    }


def _extract_error(output: str) -> dict:
    """The first ERROR yosys reported, with its location when it gave one."""
    for m in _DIAG_RE.finditer(output):
        if m.group("sev") == "ERROR":
            return _diagnostic(m, "error")
    for line in output.splitlines():
        if "syntax error" in line.lower():
            return {"file": "", "line": 0, "severity": "error", "message": line.strip()}
    return {"file": "", "line": 0, "severity": "error", "message": "Yosys synthesis failed"}


def _not_found() -> dict:
    return {
        "tool": "yosys",
        "target": "unknown",
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0, "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "netlist": None,
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": f"yosys not found.\n{install_hint('yosys')}"}],
        "raw_output": "",
    }
