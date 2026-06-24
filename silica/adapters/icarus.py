"""Icarus Verilog adapter — full SV simulation via iverilog + vvp."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# filename.sv:10: error: some message
# filename.sv:10: warning: some message
_DIAG_RE = re.compile(
    r"^([^:]+):(\d+):\s*(error|warning|note):\s*(.+)$",
    re.MULTILINE,
)


def _parse_output(text: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _DIAG_RE.finditer(text):
        file, line, severity, message = m.groups()
        entry: dict[str, Any] = {
            "file": file.strip(),
            "line": int(line),
            "severity": severity,
            "message": message.strip(),
        }
        if severity == "error":
            errors.append(entry)
        else:
            warnings.append(entry)
    return errors, warnings


def run(dut: str, testbench: str, top: str | None = None, timeout: int = 60) -> dict:
    """Compile with iverilog -g2012, then simulate with vvp."""
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if not iverilog or not vvp:
        return _not_found()

    with tempfile.TemporaryDirectory(prefix="silica_icarus_") as tmpdir:
        sim_out = Path(tmpdir) / "sim.out"

        compile_cmd = [
            iverilog,
            "-g2012",
            "-o", str(sim_out),
            testbench,
            dut,
        ]
        if top:
            compile_cmd += ["-s", top]

        cp = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        compile_errors, compile_warnings = _parse_output(cp.stdout + cp.stderr)

        if cp.returncode != 0:
            return {
                "exit_code": cp.returncode,
                "errors": compile_errors,
                "warnings": compile_warnings,
                "raw_stdout": cp.stdout,
                "raw_stderr": cp.stderr,
            }

        # Run simulation
        rp = subprocess.run(
            [vvp, str(sim_out)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(dut).parent),
        )

        run_errors, run_warnings = _parse_output(rp.stderr)
        all_errors = compile_errors + run_errors
        all_warnings = compile_warnings + run_warnings

        if rp.returncode != 0 and not run_errors:
            all_errors.append({
                "file": dut,
                "line": 0,
                "severity": "error",
                "message": f"Simulation exited with code {rp.returncode}",
            })

        return {
            "exit_code": rp.returncode,
            "errors": all_errors,
            "warnings": all_warnings,
            "raw_stdout": cp.stdout + rp.stdout,
            "raw_stderr": cp.stderr + rp.stderr,
        }


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [{
            "file": "",
            "line": 0,
            "severity": "error",
            "message": "iverilog/vvp not found. Install with: brew install icarus-verilog",
        }],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
    }
