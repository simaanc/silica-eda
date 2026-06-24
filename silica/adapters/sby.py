"""SymbiYosys (sby) adapter — formal verification front-end."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_DONE_RE = re.compile(r"DONE \((PASS|FAIL|ERROR|UNKNOWN), rc=(\d+)\)")
_ASSERT_FAIL_RE = re.compile(
    r"Assert failed in (\S+): (\S+):(\d+)"
)
_SUMMARY_FAIL_RE = re.compile(
    r"summary:\s+failed assertion (\S+) at (\S+):(\d+)"
)
_TRACE_RE = re.compile(
    r"summary: counterexample trace \[.*?\]: (.+\.(?:vcd|yw))"
)
_WARNING_RE = re.compile(
    r"(?:base|prep): (\S+):(\d+): Warning: (.+)"
)
_ERROR_RE = re.compile(
    r"(?:base|prep): (\S+):(\d+): ERROR: (.+)"
)


def _detect_solver() -> str:
    for solver in ("z3", "bitwuzla", "boolector"):
        if shutil.which(solver):
            return solver
    return ""


def run(sby_file: str, task: str | None = None, timeout: int = 300) -> dict:
    """Run sby on a .sby config file and return structured results.

    Args:
        sby_file: Path to the .sby configuration file.
        task: Optional task name (for multi-task .sby files).
        timeout: Seconds before killing sby.

    Returns a FormalResult dict:
        status: "PASS" | "FAIL" | "ERROR" | "UNKNOWN"
        rc: exit code (0=PASS, 2=FAIL, 16=ERROR)
        failures: [{module, property, file, line}]
        traces: [path to counterexample VCD]
        warnings: [{file, line, message}]
        errors: [{file, line, message}]
        workdir: path to sby work directory (persists for trace viewing)
        raw_output: full combined log
    """
    binary = shutil.which("sby")
    if not binary:
        return _not_found()

    sby_path = Path(sby_file).resolve()
    if not sby_path.exists():
        return {
            "status": "ERROR",
            "rc": -1,
            "failures": [],
            "traces": [],
            "warnings": [],
            "errors": [{"file": sby_file, "line": 0, "message": f"File not found: {sby_file}"}],
            "workdir": "",
            "raw_output": "",
        }

    # Don't pre-create the dir — sby creates it itself. We just provide the path.
    workdir = str(Path(tempfile.gettempdir()) / f"silica_sby_{sby_path.stem}")

    cmd = [binary, "-f", "-d", workdir, str(sby_path)]
    if task:
        cmd.append(task)

    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(sby_path.parent),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "UNKNOWN",
            "rc": -1,
            "failures": [],
            "traces": [],
            "warnings": [],
            "errors": [{"file": sby_file, "line": 0, "message": f"sby timed out after {timeout}s"}],
            "workdir": workdir,
            "raw_output": "",
        }

    raw = cp.stdout + cp.stderr

    # Parse final status
    status = "UNKNOWN"
    rc = cp.returncode
    m = _DONE_RE.search(raw)
    if m:
        status = m.group(1)

    # Parse failures from summary lines (most reliable — deduped by sby)
    failures = []
    seen_props: set[str] = set()
    for m in _SUMMARY_FAIL_RE.finditer(raw):
        prop, file_, line = m.group(1), m.group(2), int(m.group(3))
        key = f"{prop}@{file_}:{line}"
        if key not in seen_props:
            seen_props.add(key)
            failures.append({"property": prop, "file": file_, "line": line})

    # Parse counterexample trace paths
    traces = []
    for m in _TRACE_RE.finditer(raw):
        path = m.group(1).strip()
        if Path(path).exists():
            traces.append(path)

    # Parse warnings and errors from Yosys elaboration
    warnings = []
    for m in _WARNING_RE.finditer(raw):
        warnings.append({"file": m.group(1), "line": int(m.group(2)), "message": m.group(3).strip()})

    errors = []
    for m in _ERROR_RE.finditer(raw):
        errors.append({"file": m.group(1), "line": int(m.group(2)), "message": m.group(3).strip()})

    return {
        "status": status,
        "rc": rc,
        "failures": failures,
        "traces": traces,
        "warnings": warnings,
        "errors": errors,
        "workdir": workdir,
        "raw_output": raw,
    }


def generate_sby(
    files: list[str],
    top: str,
    mode: str = "prove",
    depth: int = 20,
    engine: str = "auto",
) -> str:
    """Generate a .sby config file content string.

    Args:
        files: List of RTL source file paths.
        top: Top module name.
        mode: "prove" | "bmc" | "cover" | "live".
        depth: Bound depth for bmc/prove.
        engine: "auto" (detect solver) | explicit engine string e.g. "smtbmc z3".
    """
    if engine == "auto":
        solver = _detect_solver()
        engine = f"smtbmc {solver}" if solver else "smtbmc"

    read_cmds = "\n".join(f"read -formal {Path(f).name}" for f in files)
    file_list = "\n".join(str(Path(f).resolve()) for f in files)

    return f"""\
[options]
mode {mode}
depth {depth}

[engines]
{engine}

[script]
{read_cmds}
prep -top {top}

[files]
{file_list}
"""


def _not_found() -> dict:
    return {
        "status": "ERROR",
        "rc": -1,
        "failures": [],
        "traces": [],
        "warnings": [],
        "errors": [{"file": "", "line": 0, "message": "sby not found. Install: brew install sby"}],
        "workdir": "",
        "raw_output": "",
    }
