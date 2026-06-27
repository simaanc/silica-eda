"""eqy adapter — equivalence checking for Yosys."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica import oss_cad_suite
from silica.adapters._hints import install_hint

_DONE_RE = re.compile(r"DONE \((PASS|FAIL|ERROR|UNKNOWN), rc=(\d+)\)")
_MISMATCH_RE = re.compile(r"Mismatch in output '(\S+)'")
_WARNING_RE = re.compile(r"Warning:\s*(.+)")
_ERROR_RE = re.compile(r"ERROR:\s*(.+)")


def run(
    eqy_file: str | None = None,
    gold_files: list[str] | None = None,
    gate_files: list[str] | None = None,
    top: str | None = None,
    timeout: int = 300,
) -> dict:
    """Run equivalence checking with eqy.

    Two usage modes:
      1. Pass eqy_file — run an existing .eqy config file directly.
      2. Pass gold_files + gate_files + top — auto-generate a config.

    Returns a FormalResult dict:
        status: "PASS" | "FAIL" | "ERROR" | "UNKNOWN"
        rc: exit code
        failures: [{property, file, line}] — equivalence mismatches
        traces: [] (eqy does not produce VCD counterexamples)
        warnings, errors, workdir, raw_output
    """
    binary = oss_cad_suite.which("eqy")
    if not binary:
        return _not_found()

    workdir = Path(tempfile.mkdtemp(prefix="silica_eqy_"))

    if eqy_file:
        eqy_path = Path(eqy_file).resolve()
        if not eqy_path.exists():
            return _error_result(f"eqy file not found: {eqy_file}", str(workdir))
    else:
        if not gold_files or not gate_files or not top:
            return _error_result(
                "Provide either eqy_file or all of: gold_files, gate_files, top.",
                str(workdir),
            )
        eqy_path = workdir / f"{top}.eqy"
        eqy_path.write_text(_generate_eqy(gold_files, gate_files, top), encoding="utf-8")

    try:
        cp = subprocess.run(
            [binary, "-f", str(eqy_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        return _error_result(f"eqy timed out after {timeout}s", str(workdir))

    raw = cp.stdout + cp.stderr

    status = "UNKNOWN"
    rc = cp.returncode
    m = _DONE_RE.search(raw)
    if m:
        status, rc = m.group(1), int(m.group(2))

    failures = [
        {"property": mm.group(1), "file": "", "line": 0}
        for mm in _MISMATCH_RE.finditer(raw)
    ]
    warnings = [{"file": "", "line": 0, "message": mm.group(1).strip()}
                for mm in _WARNING_RE.finditer(raw)]
    errors = [{"file": "", "line": 0, "message": mm.group(1).strip()}
              for mm in _ERROR_RE.finditer(raw)]

    return {
        "status": status,
        "rc": rc,
        "failures": failures,
        "traces": [],
        "warnings": warnings,
        "errors": errors,
        "workdir": str(workdir),
        "raw_output": raw,
    }


def _generate_eqy(gold_files: list[str], gate_files: list[str], top: str) -> str:
    gold_reads = "\n".join(f"read -formal {Path(f).resolve()}" for f in gold_files)
    gate_reads = "\n".join(f"read -formal {Path(f).resolve()}" for f in gate_files)
    return f"""\
[options]

[gold]
{gold_reads}
prep -top {top}

[gate]
{gate_reads}
prep -top {top}
"""


def _error_result(message: str, workdir: str) -> dict:
    return {
        "status": "ERROR",
        "rc": -1,
        "failures": [],
        "traces": [],
        "warnings": [],
        "errors": [{"file": "", "line": 0, "message": message}],
        "workdir": workdir,
        "raw_output": "",
    }


def _not_found() -> dict:
    return {
        "status": "ERROR",
        "rc": -1,
        "failures": [],
        "traces": [],
        "warnings": [],
        "errors": [{"file": "", "line": 0, "message": f"eqy not found.\n{install_hint('eqy')}"}],
        "workdir": "",
        "raw_output": "",
    }
