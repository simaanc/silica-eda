"""eqy adapter — equivalence checking for Yosys."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from silica import oss_cad_suite
from silica.adapters._hints import install_hint
from silica.adapters._script_paths import unsafe_script_value


def _eqy_cmd() -> list[str] | None:
    """Return the command prefix to invoke eqy, or None if not found."""
    if not oss_cad_suite.which("eqy"):
        return None
    if sys.platform == "win32":
        root = oss_cad_suite.find_root()
        if root:
            python3 = root / "lib" / "python3.exe"
            eqy_script = root / "bin" / "eqy-script.py"
            if python3.exists() and eqy_script.exists():
                return [str(python3), oss_cad_suite._short_path(str(eqy_script))]
    return [oss_cad_suite.which("eqy")]  # type: ignore[list-item]


_DONE_RE = re.compile(r"DONE \((PASS|FAIL|ERROR|UNKNOWN), rc=(\d+)\)")
_MISMATCH_RE = re.compile(r"Failed to prove equivalence of partition (\S+)")
_WARNING_RE = re.compile(r"Warning:\s*(.+)")
_ERROR_RE = re.compile(r"ERROR:\s*(.+)")

# Patterns for the yosys-direct equiv_* path (Windows fallback)
_EQUIV_PROVEN_RE = re.compile(r"Equivalence successfully proven!")
_EQUIV_UNPROVEN_RE = re.compile(r"Unproven \$equiv.*?: \\(\S+)")


def run(
    eqy_file: str | None = None,
    gold_files: list[str] | None = None,
    gate_files: list[str] | None = None,
    top: str | None = None,
    timeout: int = 300,
    depth: int = 20,
) -> dict:
    """Run equivalence checking with eqy.

    Two usage modes:
      1. Pass eqy_file — run an existing .eqy config file directly.
      2. Pass gold_files + gate_files + top — auto-generate a config.

    depth bounds the induction proof in the yosys-direct Windows fallback;
    that path reports it back as induction_depth (UNKNOWN there may just
    mean the bound was too shallow).

    Returns a FormalResult dict:
        status: "PASS" | "FAIL" | "ERROR" | "UNKNOWN"
        rc: exit code
        failures: [{property, file, line}] — equivalence mismatches
        traces: [] (eqy does not produce VCD counterexamples)
        warnings, errors, workdir, raw_output
    """
    if not eqy_file:
        bad = unsafe_script_value(gold_files, gate_files, top)
        if bad:
            return _error_result(bad, "")

    # On Windows, eqy's bash+make pipeline cannot run yosys due to MSYS2 pipe
    # incompatibility with native Windows binaries. When called in auto-generate
    # mode, bypass eqy entirely and run yosys equiv_* commands directly.
    if sys.platform == "win32" and not eqy_file and gold_files and gate_files and top:
        if not oss_cad_suite.which("yosys"):
            return _not_found()
        return _run_yosys_equiv(gold_files, gate_files, top, timeout, depth)

    cmd_prefix = _eqy_cmd()
    if not cmd_prefix:
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
        eqy_path.write_text(generate_eqy(gold_files, gate_files, top), encoding="utf-8")

    env = oss_cad_suite.env_with_suite()

    try:
        cp = subprocess.run(
            cmd_prefix + ["-f", str(eqy_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            env=env,
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


def _run_yosys_equiv(
    gold_files: list[str], gate_files: list[str], top: str, timeout: int,
    depth: int = 20,
) -> dict:
    """Windows fallback: equivalence check via yosys equiv_* commands (no bash needed)."""
    workdir = Path(tempfile.mkdtemp(prefix="silica_eqy_"))

    gold_reads = "\n".join(
        f'read_verilog -formal "{Path(f).resolve()}"' for f in gold_files
    )
    gate_reads = "\n".join(
        f'read_verilog -formal "{Path(f).resolve()}"' for f in gate_files
    )

    script = f"""\
{gold_reads}
hierarchy -top {top}
proc; async2sync; opt
design -save __gold_ds__

design -reset
{gate_reads}
hierarchy -top {top}
proc; async2sync; opt
design -save __gate_ds__

design -reset
design -copy-from __gold_ds__ -as __gold__ {top}
design -copy-from __gate_ds__ -as __gate__ {top}

equiv_make __gold__ __gate__ __equiv__
equiv_simple __equiv__
equiv_induct -seq {depth} __equiv__
equiv_status __equiv__
"""

    script_path = workdir / "equiv_check.ys"
    log_path = workdir / "equiv_check.log"
    script_path.write_text(script, encoding="utf-8")

    yosys_bin = oss_cad_suite.which("yosys")
    env = oss_cad_suite.env_with_suite()

    try:
        cp = subprocess.run(
            [yosys_bin, "-ql", str(log_path), str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workdir),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return _error_result(f"eqy timed out after {timeout}s", str(workdir))

    raw = log_path.read_text(encoding="utf-8") if log_path.exists() else cp.stdout + cp.stderr

    if _EQUIV_PROVEN_RE.search(raw):
        status = "PASS"
        failures = []
    elif "unproven $equiv" in raw.lower():
        status = "FAIL"
        failures = [
            {"property": m.group(1), "file": "", "line": 0}
            for m in _EQUIV_UNPROVEN_RE.finditer(raw)
        ]
    else:
        status = "UNKNOWN"
        failures = []

    warnings = [{"file": "", "line": 0, "message": m.group(1).strip()}
                for m in _WARNING_RE.finditer(raw)]
    errors = [{"file": "", "line": 0, "message": m.group(1).strip()}
              for m in _ERROR_RE.finditer(raw)]

    return {
        "status": status,
        "rc": cp.returncode,
        "failures": failures,
        "traces": [],
        "warnings": warnings,
        "errors": errors,
        "workdir": str(workdir),
        "raw_output": raw,
        # Bounded induction: UNKNOWN can mean the proof needs a deeper bound.
        "induction_depth": depth,
    }


def generate_eqy(gold_files: list[str], gate_files: list[str], top: str) -> str:
    # The sby strategy, not sat: eqy's sat strategy proves sequential
    # partitions equivalent even when their next-state logic differs
    # (an up-counter vs a down-counter passes).
    gold_reads = "\n".join(f'read -formal "{Path(f).resolve()}"' for f in gold_files)
    gate_reads = "\n".join(f'read -formal "{Path(f).resolve()}"' for f in gate_files)
    return f"""\
[options]

[gold]
{gold_reads}
prep -top {top}

[gate]
{gate_reads}
prep -top {top}

[strategy sby]
use sby
depth 10
engine smtbmc
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
