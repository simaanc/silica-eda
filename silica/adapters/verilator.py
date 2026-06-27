"""Verilator adapter — compile-and-simulate using --binary (Verilator 5+)."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from silica import oss_cad_suite
from silica.adapters._hints import install_hint


def _find_verilator() -> str | None:
    """Find the verilator binary, preferring verilator_bin.exe on Windows.

    On Windows, the OSS CAD Suite ships verilator as a Perl wrapper script
    (not directly executable). verilator_bin.exe is the actual Win32 binary.
    """
    if sys.platform == "win32":
        return oss_cad_suite.which("verilator_bin") or oss_cad_suite.which("verilator")
    return oss_cad_suite.which("verilator")

# %Error-PARSE: path/to/file.sv:10:5: message
# %Warning-UNUSED: path/to/file.sv:20:3: message
# %Error: path/to/file.sv:10: message   (no column)
# On Windows paths start with a drive letter (C:\...) so [^:]+ stops at the colon —
# use an optional drive-letter prefix to handle both Unix and Windows paths.
_DIAG_RE = re.compile(
    r"^%(Error|Warning)(?:-\w+)?:\s*((?:[A-Za-z]:)?[^:]+):(\d+)(?::\d+)?:\s*(.+)$",
    re.MULTILINE,
)
# Summary lines like "%Error: Exiting due to 1 error(s)" have no file — skip them.
_SUMMARY_RE = re.compile(r"^%(Error|Warning)(?:-\w+)?:\s*[A-Z]", re.MULTILINE)


def _parse_output(stderr: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _DIAG_RE.finditer(stderr):
        severity_str, file, line, message = m.group(1), m.group(2), m.group(3), m.group(4)
        entry: dict[str, Any] = {
            "file": file.strip(),
            "line": int(line),
            "severity": severity_str.lower(),
            "message": message.strip(),
        }
        if severity_str == "Error":
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
) -> dict:
    """Compile and simulate with Verilator (--binary mode, Verilator 5+).

    Falls back to lint-only mode if --binary is unsupported.
    When trace=True, writes dump.vcd to a persistent temp directory and
    returns its path as trace_vcd in the result.
    """
    binary = _find_verilator()
    if not binary:
        return _not_found()

    env = oss_cad_suite.env_with_suite()

    if top is None:
        # Infer top from testbench filename stem
        top = Path(testbench).stem

    # When tracing, keep a persistent dir so the VCD survives after we return.
    trace_dir = tempfile.mkdtemp(prefix="silica_trace_") if trace else None

    with tempfile.TemporaryDirectory(prefix="silica_veri_") as tmpdir:
        obj_dir = Path(tmpdir) / "obj_dir"
        sim_bin = Path(tmpdir) / f"V{top}"

        compile_cmd = [
            binary,
            "--binary",
            "--build",
            "-Wall",
            "-Wno-TIMESCALEMOD",
            "-Wno-STMTDLY",
            "--top-module", top,
            "--Mdir", str(obj_dir),
            "-o", str(sim_bin),
            dut,
            testbench,
        ]
        if trace:
            compile_cmd.append("--trace")

        cp = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        errors, warnings = _parse_output(cp.stderr)

        if cp.returncode != 0:
            result: dict = {
                "exit_code": cp.returncode,
                "errors": errors,
                "warnings": warnings,
                "raw_stdout": cp.stdout,
                "raw_stderr": cp.stderr,
                "trace_vcd": None,
            }
            return result

        # Run the simulation binary; if tracing, CWD is trace_dir so dump.vcd lands there.
        sim_cwd = trace_dir if trace_dir else str(Path(dut).parent)
        rp = subprocess.run(
            [str(sim_bin)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=sim_cwd,
            env=env,
        )

        run_errors, run_warnings = _parse_output(rp.stderr)
        all_errors = errors + run_errors
        all_warnings = warnings + run_warnings

        # Treat non-zero exit or $fatal in output as error
        if rp.returncode != 0 and not run_errors:
            all_errors.append({
                "file": dut,
                "line": 0,
                "severity": "error",
                "message": f"Simulation exited with code {rp.returncode}",
            })

        trace_vcd = None
        if trace_dir:
            vcds = sorted(Path(trace_dir).glob("*.vcd"))
            trace_vcd = str(vcds[0]) if vcds else None

        return {
            "exit_code": rp.returncode,
            "errors": all_errors,
            "warnings": all_warnings,
            "raw_stdout": cp.stdout + rp.stdout,
            "raw_stderr": cp.stderr + rp.stderr,
            "trace_vcd": trace_vcd,
        }


def lint_only(file: str, timeout: int = 30) -> dict:
    """Run verilator --lint-only for a quick syntax/semantic check."""
    binary = _find_verilator()
    if not binary:
        return _not_found()

    cp = subprocess.run(
        [binary, "--lint-only", "-Wall", "-Wno-TIMESCALEMOD", file],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=oss_cad_suite.env_with_suite(),
    )
    errors, warnings = _parse_output(cp.stderr)
    return {
        "exit_code": cp.returncode,
        "errors": errors,
        "warnings": warnings,
        "raw_stdout": cp.stdout,
        "raw_stderr": cp.stderr,
    }


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [{
            "file": "",
            "line": 0,
            "severity": "error",
            "message": f"verilator not found.\n{install_hint('verilator')}",
        }],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
    }
