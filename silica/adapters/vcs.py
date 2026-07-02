"""VCS adapter — Synopsys VCS SystemVerilog simulation."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.tools._config_dispatch import resolve

# VCS compile diagnostics — simple line-based pass for severity
# Error-[SE] Syntax error ...
# Error: filename.sv:10: message
_LINE_RE = re.compile(
    r"^(Error(?:-\[\w+\])?|Warning(?:-\[\w+\])?):\s*(.+)$",
    re.MULTILINE,
)


def _parse_output(text: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _LINE_RE.finditer(text):
        sev_raw, message = m.group(1), m.group(2).strip()
        sev = "error" if sev_raw.lower().startswith("error") else "warning"
        entry = {"file": "", "line": 0, "severity": sev, "message": message}
        if sev == "error":
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
    """Compile with vcs -sverilog, then simulate with ./simv."""
    vcs = resolve("vcs")
    if not vcs:
        return _not_found()

    with tempfile.TemporaryDirectory(prefix="silica_vcs_") as tmpdir:
        simv = str(Path(tmpdir) / "simv")
        csrc = str(Path(tmpdir) / "csrc")

        compile_cmd = [
            vcs,
            "-sverilog", "-full64",
            "-o", simv,
            "-Mdir", csrc,
        ]
        if top:
            compile_cmd += ["-top", top]
        compile_cmd += [testbench, dut]

        cp = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
        )

        compile_errors, compile_warnings = _parse_output(cp.stdout + cp.stderr)

        if cp.returncode != 0:
            return {
                "exit_code": cp.returncode,
                "errors": compile_errors or [_generic_error(dut, "VCS compilation failed")],
                "warnings": compile_warnings,
                "raw_stdout": cp.stdout,
                "raw_stderr": cp.stderr,
                "trace_vcd": None,
            }

        # Persistent trace dir, created only after a successful compile so
        # failed runs don't leak dirs.
        trace_dir = tempfile.mkdtemp(prefix="silica_trace_") if trace else None

        sim_cmd = [simv]
        if trace:
            sim_cmd += ["+vcs+vc+dumpfile+dump.vcd"]

        sim_cwd = trace_dir if trace_dir else str(Path(dut).parent)
        rp = subprocess.run(
            sim_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=sim_cwd,
        )

        run_errors, run_warnings = _parse_output(rp.stdout + rp.stderr)
        all_errors = compile_errors + run_errors
        all_warnings = compile_warnings + run_warnings

        if rp.returncode != 0 and not run_errors:
            all_errors.append(_generic_error(dut, f"Simulation exited with code {rp.returncode}"))

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


def _generic_error(file: str, message: str) -> dict:
    return {"file": file, "line": 0, "severity": "error", "message": message}


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [_generic_error("", "vcs not found. VCS requires a Synopsys license — contact your vendor.")],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }
