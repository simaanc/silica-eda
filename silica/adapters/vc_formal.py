"""VC Formal adapter — Synopsys VC Formal verification."""

import re
import subprocess
from pathlib import Path
from tempfile import mkdtemp

from silica.adapters._script_paths import unsafe_script_value
from silica.detect import resolve

# VC Formal output
# Assertion PASS/FAIL summary lines
_STATUS_RE = re.compile(r"Overall FV result\s*:\s*(PASS|FAIL|INCOMPLETE|ERROR)", re.IGNORECASE)
_PROP_RE = re.compile(
    r"^\s*(PROVEN|FALSIFIED|COVERED|VACUOUS)\s+(\S+)", re.MULTILINE
)
_MSG_RE = re.compile(r"^(Error|Warning):\s*(.+)$", re.MULTILINE)
_TRACE_RE = re.compile(r"Counterexample:\s*(\S+\.vcd)", re.IGNORECASE)


def _make_tcl(top: str, files: list[str], mode: str, depth: int) -> str:
    read_cmds = "\n".join(f"read_sverilog {{{f}}}" for f in files)
    prove_cmd = {
        "prove":  f"check_fv -prove -depth {depth}",
        "bmc":    f"check_fv -bmc -depth {depth}",
        "cover":  "check_fv -cover",
    }.get(mode, f"check_fv -prove -depth {depth}")

    return f"""\
{read_cmds}
elaborate -top {top}
{prove_cmd}
report_fv -list
exit
"""


def run(
    sby_file: str | None = None,
    files: list[str] | None = None,
    top: str | None = None,
    mode: str = "prove",
    depth: int = 20,
    timeout: int = 300,
    **kwargs,
) -> dict:
    """Run VC Formal in batch mode via a generated or supplied TCL script."""
    if not sby_file:
        bad = unsafe_script_value(files, top)
        if bad:
            return _error_result(bad)

    binary = resolve("vc_formal")
    if not binary:
        return _not_found()

    tmpdir = mkdtemp(prefix="silica_vcf_")
    if sby_file:
        tcl_path = sby_file
        work_cwd = str(Path(sby_file).parent)
    else:
        if not files or not top:
            return _error_result("Provide either sby_file or both files + top.")
        tcl_path = str(Path(tmpdir) / f"{top}.tcl")
        Path(tcl_path).write_text(_make_tcl(top, files, mode, depth), encoding="utf-8")
        work_cwd = tmpdir

    try:
        cp = subprocess.run(
            [binary, "-f", tcl_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_cwd,
        )
    except subprocess.TimeoutExpired:
        # A hung tool must not crash the MCP server — report it structurally.
        return _error_result(f"vc_formal timed out after {timeout}s")

    raw = cp.stdout + cp.stderr

    status_m = _STATUS_RE.search(raw)
    if status_m:
        raw_status = status_m.group(1).upper()
        status = {"PASS": "PASS", "FAIL": "FAIL"}.get(raw_status, "UNKNOWN")
    else:
        status = "UNKNOWN" if cp.returncode == 0 else "ERROR"

    failures = [
        {"property": m.group(2), "file": "", "line": 0}
        for m in _PROP_RE.finditer(raw)
        if m.group(1).upper() == "FALSIFIED"
    ]

    traces = [
        m.group(1) for m in _TRACE_RE.finditer(raw)
        if (Path(m.group(1)).exists() or (Path(work_cwd) / m.group(1)).exists())
    ]

    errors, warnings = [], []
    for m in _MSG_RE.finditer(raw):
        sev, msg = m.groups()
        entry = {"file": "", "line": 0, "message": msg.strip()}
        if sev == "Error":
            errors.append(entry)
        else:
            warnings.append(entry)

    if cp.returncode != 0 and not errors and status == "ERROR":
        errors.append({"file": "", "line": 0, "message": f"vc_formal exited with code {cp.returncode}"})

    return {
        "status": status,
        "rc": cp.returncode,
        "failures": failures,
        "traces": traces,
        "warnings": warnings,
        "errors": errors,
        "workdir": tmpdir,
        "raw_output": raw,
    }


def _error_result(message: str) -> dict:
    return {
        "status": "ERROR",
        "rc": -1,
        "failures": [],
        "traces": [],
        "warnings": [],
        "errors": [{"file": "", "line": 0, "message": message}],
        "workdir": "",
        "raw_output": "",
    }


def _not_found() -> dict:
    return _error_result("vcf/vc_formal not found. VC Formal requires a Synopsys license.")
