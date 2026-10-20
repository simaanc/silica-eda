"""Xcelium adapter — Cadence Xcelium SystemVerilog simulation."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.detect import resolve

# xmvlog: *E,SYNTAX (filename.sv,10|0): message
# xmelab: *W,DSEM2009 (filename.sv,10|0): message
# xmsim: *E,DSFAIL: message
_DIAG_RE = re.compile(
    r"^\w+:\s*\*(E|W),\w+\s*(?:\(([^,]+),(\d+)[^)]*\))?:\s*(.+)$",
    re.MULTILINE,
)


def _parse_output(text: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _DIAG_RE.finditer(text):
        level, file_, line_s, message = m.groups()
        entry = {
            "file": (file_ or "").strip(),
            "line": int(line_s) if line_s else 0,
            "severity": "error" if level == "E" else "warning",
            "message": message.strip(),
        }
        if level == "E":
            errors.append(entry)
        else:
            warnings.append(entry)
    return errors, warnings


def run(
    dut: str,
    testbench: str,
    top: str | None = None,
    timeout: int = 60,
    trace: bool = False,
    extra_sources: list[str] | None = None,
) -> dict:
    """Compile and simulate with xrun (Xcelium unified flow)."""
    try:
        return _run(dut, testbench, top, timeout, trace, extra_sources or [])
    except subprocess.TimeoutExpired:
        # A hung tool must not crash the MCP server — report it structurally.
        return _timeout_result(dut, timeout)


def _run(
    dut: str,
    testbench: str,
    top: str | None,
    timeout: int,
    trace: bool,
    extra_sources: list[str],
) -> dict:
    xrun = resolve("xcelium")  # resolves xrun or irun
    if not xrun:
        return _not_found()

    top_mod = top or Path(testbench).stem
    trace_dir = tempfile.mkdtemp(prefix="silica_trace_") if trace else None

    # xrun compiles and simulates in one step. Run it in the DUT's directory,
    # as the other simulators do, so relative paths in the testbench
    # ($readmemh) resolve from there; give it absolute source paths, and keep
    # the xcelium.d build directory and the log in the temp dir.
    # Unverified: no Xcelium install was available to confirm -xmlibdirpath;
    # xrun may still write xrun.history (and xrun.key) into the DUT's directory.
    sources = [str(Path(f).resolve()) for f in (testbench, dut, *extra_sources)]

    with tempfile.TemporaryDirectory(prefix="silica_xcelium_") as tmpdir:
        cmd = [xrun, "-sv", "-64bit",
               "-xmlibdirpath", tmpdir,
               "-l", str(Path(tmpdir) / "xrun.log"),
               "-top", top_mod, *sources]
        if trace:
            vcd_path = str(Path(trace_dir) / "dump.vcd") if trace_dir else "dump.vcd"
            cmd += [
                "-access", "+rw",
                "-input",
                f"database -open -vcd {vcd_path} -timescale ns; "
                "probe -create -all -vcd -depth all",
            ]

        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(dut).parent),
        )

    combined = cp.stdout + cp.stderr
    errors, warnings = _parse_output(combined)

    if cp.returncode != 0 and not errors:
        errors.append({"file": dut, "line": 0, "severity": "error",
                        "message": f"xrun exited with code {cp.returncode}"})

    trace_vcd = None
    if trace_dir:
        vcds = sorted(Path(trace_dir).glob("*.vcd"))
        trace_vcd = str(vcds[0]) if vcds else None

    return {
        "exit_code": cp.returncode,
        "errors": errors,
        "warnings": warnings,
        "raw_stdout": cp.stdout,
        "raw_stderr": cp.stderr,
        "trace_vcd": trace_vcd,
    }


def _timeout_result(file: str, timeout: int) -> dict:
    return {
        "exit_code": -1,
        "errors": [{"file": file, "line": 0, "severity": "error",
                    "message": f"xrun timed out after {timeout}s"}],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": "xrun/irun not found. Xcelium requires a Cadence license."}],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }
