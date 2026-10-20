"""Icarus Verilog adapter — full SV simulation via iverilog + vvp."""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from silica import oss_cad_suite
from silica.adapters import _sim_output
from silica.adapters._hints import install_hint

# filename.sv:10: error: some message
# filename.sv:10: warning: some message
# On Windows, paths start with a drive letter (C:\...) so [^:]+ would stop at the colon.
# severity keyword is optional — iverilog emits "syntax error" without an explicit "error:" prefix.
_DIAG_RE = re.compile(
    r"^((?:[A-Za-z]:)?[^:]+):(\d+):\s*(?:(error|warning|note):\s*)?(.+)$",
    re.MULTILINE,
)

# vvp prints $error/$fatal/$warning and its own runtime errors to stdout:
#   FATAL: tb.sv:102: LEDs 1 at tick 16, expected 0
#   ERROR: soc.sv:80: $readmemh: Unable to open fw.hex for reading.
_RUNTIME_RE = re.compile(
    r"^(ERROR|FATAL|WARNING): ((?:[A-Za-z]:)?[^:]+):(\d+): (.+)$",
    re.MULTILINE,
)


def _parse_runtime(text: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _RUNTIME_RE.finditer(text):
        entry: dict[str, Any] = {
            "file": m.group(2).strip(),
            "line": int(m.group(3)),
            "severity": "warning" if m.group(1) == "WARNING" else "error",
            "message": m.group(4).strip(),
        }
        (warnings if m.group(1) == "WARNING" else errors).append(entry)
    return errors, warnings


def _parse_output(text: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _DIAG_RE.finditer(text):
        file_str, line_str, sev, msg = m.group(1), m.group(2), m.group(3), m.group(4)
        if sev is None:
            msg_lower = msg.strip().lower()
            if "error" in msg_lower:
                sev = "error"
            elif "warning" in msg_lower:
                sev = "warning"
            else:
                continue  # skip noise (e.g. "I give up.")
        entry: dict[str, Any] = {
            "file": file_str.strip(),
            "line": int(line_str),
            "severity": sev,
            "message": msg.strip(),
        }
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
    extra_sources: list[str] | None = None,
) -> dict:
    """Compile with iverilog -g2012, then simulate with vvp.

    When trace=True, runs the simulation in a persistent temp directory so
    any $dumpfile VCD written by the testbench survives. Returns trace_vcd
    pointing to the first .vcd found in that directory.

    extra_sources: additional design files (submodules, packages) compiled
    alongside dut and testbench.
    """
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
    iverilog = oss_cad_suite.which("iverilog")
    vvp = oss_cad_suite.which("vvp")
    if not iverilog or not vvp:
        return _not_found()

    env = oss_cad_suite.env_with_suite()

    with tempfile.TemporaryDirectory(prefix="silica_icarus_") as tmpdir:
        sim_out = Path(tmpdir) / "sim.out"

        compile_cmd = [
            iverilog,
            "-g2012",
            "-o", str(sim_out),
        ]
        if top:
            compile_cmd += ["-s", top]
        compile_cmd += [testbench, dut, *extra_sources]

        cp = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        compile_errors, compile_warnings = _parse_output(cp.stdout + cp.stderr)

        if cp.returncode != 0:
            return {
                "exit_code": cp.returncode,
                "errors": compile_errors,
                "warnings": compile_warnings,
                "raw_stdout": cp.stdout,
                "raw_stderr": cp.stderr,
                "trace_vcd": None,
            }

        # Persistent dir for trace output; not auto-cleaned so caller can open the VCD.
        # Created only after a successful compile so failed runs don't leak dirs.
        trace_dir = tempfile.mkdtemp(prefix="silica_trace_") if trace else None

        # Run in the DUT's directory either way, so relative paths in the
        # testbench ($readmemh) don't depend on tracing; VCDs move afterwards.
        sim_cwd = str(Path(dut).parent)
        vcds_before = _sim_output.snapshot(sim_cwd) if trace_dir else {}
        rp = subprocess.run(
            [vvp, str(sim_out)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=sim_cwd,
            env=env,
        )

        run_errors, run_warnings = _parse_runtime(rp.stdout + rp.stderr)
        all_errors = compile_errors + run_errors
        all_warnings = compile_warnings + run_warnings

        if rp.returncode != 0 and not run_errors:
            all_errors.append({
                "file": dut,
                "line": 0,
                "severity": "error",
                "message": f"Simulation exited with code {rp.returncode}",
            })

        trace_vcd = None
        if trace_dir:
            vcds = _sim_output.move_written(sim_cwd, vcds_before, trace_dir)
            trace_vcd = str(vcds[0]) if vcds else None

        return {
            "exit_code": rp.returncode,
            "errors": all_errors,
            "warnings": all_warnings,
            "raw_stdout": cp.stdout + rp.stdout,
            "raw_stderr": cp.stderr + rp.stderr,
            "trace_vcd": trace_vcd,
        }


def _timeout_result(file: str, timeout: int) -> dict:
    return {
        "exit_code": -1,
        "errors": [{"file": file, "line": 0, "severity": "error",
                    "message": f"iverilog/vvp timed out after {timeout}s"}],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [{
            "file": "",
            "line": 0,
            "severity": "error",
            "message": f"iverilog/vvp not found.\n{install_hint('iverilog')}",
        }],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
    }
