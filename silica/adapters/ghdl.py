"""GHDL adapter — VHDL simulation."""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from silica import oss_cad_suite
from silica.adapters._hints import install_hint

# <file>:<line>:<col>: error: <msg>
# <file>:<line>:<col>: warning[<name>]: <msg>
_DIAG_RE = re.compile(
    r"^([^:]+):(\d+):\d+:\s*(error|warning|note)(?:\[[\w-]+\])?:\s*(.+)$",
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


def run(
    dut: str,
    testbench: str,
    top: str | None = None,
    timeout: int = 60,
    trace: bool = False,
    std: str = "08",
    stop_time: str | None = None,
) -> dict:
    """Analyze, elaborate, and run a VHDL design with GHDL.

    Args:
        dut: Path to the DUT VHDL source file.
        testbench: Path to the testbench VHDL file.
        top: Top-level entity name. Inferred from testbench filename if omitted.
        timeout: Seconds before killing GHDL.
        trace: When True, capture a VCD waveform. Returns trace_vcd path.
        std: VHDL standard — "87" | "93" | "00" | "02" | "08". Default "08".
        stop_time: Simulation stop time e.g. "1ms", "100us". Optional.
    """
    binary = oss_cad_suite.which("ghdl")
    if not binary:
        return _not_found()

    top_entity = top or Path(testbench).stem
    std_flag = f"--std={std}"
    files = [str(Path(dut).resolve()), str(Path(testbench).resolve())]
    if dut == testbench:
        files = [str(Path(dut).resolve())]

    trace_dir = tempfile.mkdtemp(prefix="silica_ghdl_trace_") if trace else None
    env = oss_cad_suite.env_with_suite()

    with tempfile.TemporaryDirectory(prefix="silica_ghdl_") as workdir:
        # Step 1: analyze
        ap = subprocess.run(
            [binary, "-a", std_flag] + files,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            env=env,
        )
        analyze_errors, analyze_warnings = _parse_output(ap.stdout + ap.stderr)

        if ap.returncode != 0:
            return {
                "exit_code": ap.returncode,
                "errors": analyze_errors,
                "warnings": analyze_warnings,
                "raw_stdout": ap.stdout,
                "raw_stderr": ap.stderr,
                "trace_vcd": None,
            }

        # Step 2: elaborate
        ep = subprocess.run(
            [binary, "-e", std_flag, top_entity],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            env=env,
        )
        elab_errors, elab_warnings = _parse_output(ep.stdout + ep.stderr)

        if ep.returncode != 0:
            return {
                "exit_code": ep.returncode,
                "errors": analyze_errors + elab_errors,
                "warnings": analyze_warnings + elab_warnings,
                "raw_stdout": ap.stdout + ep.stdout,
                "raw_stderr": ap.stderr + ep.stderr,
                "trace_vcd": None,
            }

        # Step 3: run
        trace_path = str(Path(trace_dir) / "trace.vcd") if trace_dir else None
        run_cmd = [binary, "-r", std_flag, top_entity]
        if trace_path:
            run_cmd.append(f"--vcd={trace_path}")
        if stop_time:
            run_cmd.append(f"--stop-time={stop_time}")

        rp = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            env=env,
        )
        run_errors, run_warnings = _parse_output(rp.stdout + rp.stderr)

        if rp.returncode != 0 and not run_errors:
            run_errors.append({
                "file": testbench,
                "line": 0,
                "severity": "error",
                "message": f"Simulation exited with code {rp.returncode}",
            })

        trace_vcd = trace_path if (trace_path and Path(trace_path).exists()) else None

        return {
            "exit_code": rp.returncode,
            "errors": analyze_errors + elab_errors + run_errors,
            "warnings": analyze_warnings + elab_warnings + run_warnings,
            "raw_stdout": ap.stdout + ep.stdout + rp.stdout,
            "raw_stderr": ap.stderr + ep.stderr + rp.stderr,
            "trace_vcd": trace_vcd,
        }


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [{
            "file": "",
            "line": 0,
            "severity": "error",
            "message": f"ghdl not found.\n{install_hint('ghdl')}",
        }],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }
