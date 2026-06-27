"""JasperGold adapter — Cadence JasperGold formal verification."""

import re
import subprocess
import tempfile
from pathlib import Path
from tempfile import mkdtemp

from silica.tools._config_dispatch import resolve

# JasperGold output patterns
# FV Status : Proven / Falsified / Inconclusive
_STATUS_RE = re.compile(r"FV Status\s*:\s*(Proven|Falsified|Inconclusive|Aborted)", re.IGNORECASE)
_PROP_FAIL_RE = re.compile(
    r"<(\w+)>\s+(Falsified|Bounded proof|Unreachable)\s+.*?(?:at time (\d+))?", re.IGNORECASE
)
# JasperGold message format
# ERROR:  message
# WARNING:  message
_MSG_RE = re.compile(r"^(ERROR|WARNING):\s+(.+)$", re.MULTILINE)
# Counterexample trace path
_TRACE_RE = re.compile(r"(?:counterexample|trace)\s+(?:file\s+)?['\"]?(\S+\.vcd)['\"]?", re.IGNORECASE)


def _make_tcl(top: str, files: list[str], mode: str, depth: int, clock: str, reset: str) -> str:
    analyze_cmds = "\n".join(f"analyze -sv09 {{{f}}}" for f in files)
    prop_check = {
        "prove":  f"prove -property {{*}} -init {{reset}} -bg",
        "bmc":    f"prove -property {{*}} -depth {depth}",
        "cover":  f"cover -property {{*}}",
    }.get(mode, f"prove -property {{*}} -bg")

    return f"""\
{analyze_cmds}
elaborate -top {top}
clock {clock}
reset {reset}
{prop_check}
report -property -list
exit
"""


def run(
    sby_file: str | None = None,
    files: list[str] | None = None,
    top: str | None = None,
    mode: str = "prove",
    depth: int = 20,
    timeout: int = 300,
    clock: str = "clk",
    reset: str = "~rst_n",
) -> dict:
    """Run JasperGold formal verification in batch mode.

    When sby_file is provided, run it directly (as a TCL script path).
    Otherwise, generate a minimal TCL from files/top/mode.
    """
    jg = resolve("jaspergold")
    if not jg:
        return _not_found()

    tmpdir = mkdtemp(prefix="silica_jg_")
    if sby_file:
        tcl_path = sby_file
        work_cwd = str(Path(sby_file).parent)
    else:
        if not files or not top:
            return _error_result("Provide either sby_file or both files + top.")
        tcl_path = str(Path(tmpdir) / f"{top}.tcl")
        Path(tcl_path).write_text(
            _make_tcl(top, files, mode, depth, clock, reset),
            encoding="utf-8",
        )
        work_cwd = tmpdir

    cp = subprocess.run(
        [jg, "-batch", "-tcl", tcl_path, "-proj", str(Path(tmpdir) / "proj")],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=work_cwd,
    )

    raw = cp.stdout + cp.stderr

    # Parse status
    status_m = _STATUS_RE.search(raw)
    if status_m:
        raw_status = status_m.group(1).lower()
        status = "PASS" if raw_status == "proven" else "FAIL" if raw_status == "falsified" else "UNKNOWN"
    else:
        status = "UNKNOWN" if cp.returncode == 0 else "ERROR"

    failures = []
    for m in _PROP_FAIL_RE.finditer(raw):
        prop, result, time = m.groups()
        if result.lower() in ("falsified", "bounded proof"):
            failures.append({"property": prop, "file": "", "line": 0})

    traces = [
        m.group(1) for m in _TRACE_RE.finditer(raw)
        if (Path(m.group(1)).exists() or (Path(work_cwd) / m.group(1)).exists())
    ]

    errors = []
    warnings = []
    for m in _MSG_RE.finditer(raw):
        sev, msg = m.groups()
        entry = {"file": "", "line": 0, "message": msg.strip()}
        if sev == "ERROR":
            errors.append(entry)
        else:
            warnings.append(entry)

    if cp.returncode != 0 and not errors and status == "ERROR":
        errors.append({"file": "", "line": 0, "message": f"JasperGold exited with code {cp.returncode}"})

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
    return _error_result("jg/jaspergold not found. JasperGold requires a Cadence license.")
