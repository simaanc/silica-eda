"""SymbiYosys (sby) adapter — formal verification front-end."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from silica import oss_cad_suite
from silica.adapters._hints import install_hint

_DONE_RE = re.compile(r"DONE \((PASS|FAIL|ERROR|UNKNOWN), rc=(\d+)\)")
_ASSERT_FAIL_RE = re.compile(
    r"Assert failed in (\S+): (\S+):(\d+)"
)
_SUMMARY_FAIL_RE = re.compile(
    r"summary:\s+failed assertion (\S+) at (\S+):(\d+)"
)
# "[basecase]" / "[bmc]" traces are real counterexamples; an "[induction]"
# trace only shows the induction step starting from an unreachable state.
_TRACE_RE = re.compile(
    r"summary: counterexample trace \[(.*?)\]: (.+\.(?:vcd|yw))"
)
_WARNING_RE = re.compile(
    r"(?:base|prep): (\S+):(\d+): Warning: (.+)"
)
_ERROR_RE = re.compile(
    r"(?:base|prep): (\S+):(\d+): ERROR: (.+)"
)


def _sby_cmd() -> list[str] | None:
    """Return the command prefix to invoke sby.

    On Windows, sby.exe is a Python launcher that may fail to locate the
    bundled python3.exe. We detect this case and fall back to calling
    python3.exe + sby-script.py directly from the suite root."""
    if not oss_cad_suite.which("sby"):
        return None
    if sys.platform == "win32":
        root = oss_cad_suite.find_root()
        if root:
            python3 = root / "lib" / "python3.exe"
            sby_script = root / "bin" / "sby-script.py"
            if python3.exists() and sby_script.exists():
                return [str(python3), str(sby_script)]
    return [oss_cad_suite.which("sby")]  # type: ignore[list-item]


def _detect_solver() -> str:
    for solver in ("z3", "bitwuzla", "boolector", "yices-smt2"):
        if oss_cad_suite.which(solver):
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
        failures: [{module, property, file, line}] — reachable violations only
        traces: [path to counterexample VCD]
        induction_failures: [{property, file, line}] — assertions the
            k-induction step could not prove (an UNKNOWN prove), not bugs
        induction_traces: [path to the induction-step VCD]
        warnings: [{file, line, message}]
        errors: [{file, line, message}]
        workdir: path to sby work directory (persists for trace viewing)
        raw_output: full combined log
    """
    cmd_prefix = _sby_cmd()
    if not cmd_prefix:
        return _not_found()

    sby_path = Path(sby_file).resolve()
    if not sby_path.exists():
        return {
            "status": "ERROR",
            "rc": -1,
            "failures": [],
            "traces": [],
            "induction_failures": [],
            "induction_traces": [],
            "warnings": [],
            "errors": [{"file": sby_file, "line": 0, "message": f"File not found: {sby_file}"}],
            "workdir": "",
            "raw_output": "",
        }

    # Unique parent dir so two runs sharing a .sby stem can't clobber each
    # other's workdir (and traces). mkdtemp creates only the parent; the leaf
    # workdir stays uncreated so sby makes it itself (it dies on a pre-made -d).
    parent = tempfile.mkdtemp(prefix="silica_sby_")
    workdir = str(Path(parent) / sby_path.stem)

    cmd = cmd_prefix + ["-f", "-d", workdir, str(sby_path)]
    if task:
        cmd.append(task)

    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(sby_path.parent),
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "UNKNOWN",
            "rc": -1,
            "failures": [],
            "traces": [],
            "induction_failures": [],
            "induction_traces": [],
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

    # Parse failures and traces from the summary (most reliable — deduped by
    # sby). Each "failed assertion" line follows the trace it belongs to;
    # those under an induction trace go to induction_* so an UNKNOWN proof
    # doesn't read as a failure.
    failures: list[dict] = []
    traces: list[str] = []
    induction_failures: list[dict] = []
    induction_traces: list[str] = []
    seen_props: set[str] = set()
    in_induction = False
    for text in raw.splitlines():
        m = _TRACE_RE.search(text)
        if m:
            in_induction = m.group(1) == "induction"
            path = m.group(2).strip()
            if Path(path).exists():
                (induction_traces if in_induction else traces).append(path)
            continue
        m = _SUMMARY_FAIL_RE.search(text)
        if m:
            prop, file_, line = m.group(1), m.group(2), int(m.group(3))
            key = f"{in_induction}:{prop}@{file_}:{line}"
            if key not in seen_props:
                seen_props.add(key)
                entry = {"property": prop, "file": file_, "line": line}
                (induction_failures if in_induction else failures).append(entry)

    # Parse warnings and errors from Yosys elaboration
    warnings = []
    for m in _WARNING_RE.finditer(raw):
        warnings.append({"file": m.group(1), "line": int(m.group(2)),
                         "message": m.group(3).strip()})

    errors = []
    for m in _ERROR_RE.finditer(raw):
        errors.append({"file": m.group(1), "line": int(m.group(2)), "message": m.group(3).strip()})

    return {
        "status": status,
        "rc": rc,
        "failures": failures,
        "traces": traces,
        "induction_failures": induction_failures,
        "induction_traces": induction_traces,
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

    Raises:
        ValueError: if two source files share a basename. The [files] section
            uses basenames (drive letters break sby), so same-named files from
            different directories would clobber each other in the workdir — one
            silently shadowing the other. Fail loudly instead.
    """
    seen: dict[str, str] = {}
    for f in files:
        name = Path(f).name
        if name in seen and seen[name] != f:
            raise ValueError(
                f"Duplicate source basename {name!r}: {seen[name]!r} and {f!r}. "
                "sby's [files] section keys on basenames, so these would "
                "collide in the workdir — rename one or pass distinct names."
            )
        seen[name] = f

    if engine == "auto":
        solver = _detect_solver()
        engine = f"smtbmc {solver}" if solver else "smtbmc"

    read_cmds = "\n".join(f"read -formal {Path(f).name}" for f in files)
    # sby copies [files] entries into the workdir using the basename as destination.
    # Absolute paths with drive letters (C:\...) break on Windows, so use basenames.
    # This assumes sby is invoked with cwd set to the directory containing the source files.
    file_list = "\n".join(Path(f).name for f in files)

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
        "induction_failures": [],
        "induction_traces": [],
        "warnings": [],
        "errors": [{"file": "", "line": 0, "message": f"sby not found.\n{install_hint('sby')}"}],
        "workdir": "",
        "raw_output": "",
    }
