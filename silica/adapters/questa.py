"""Questa adapter — Siemens EDA Questa/ModelSim simulation."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.detect import resolve

# vlog: ** Error: filename.sv(10): message
# vsim: ** Fatal: filename.sv(10): message at time Ns
_DIAG_RE = re.compile(
    r"^\*\*\s*(Error|Warning|Fatal)(?:\s+\(\w+-\d+\))?:\s*(?:([^(]+)\((\d+)\):\s*)?(.+)$",
    re.MULTILINE,
)


def _parse_output(text: str) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    for m in _DIAG_RE.finditer(text):
        sev_raw, file_, line_s, message = m.groups()
        sev = "error" if sev_raw in ("Error", "Fatal") else "warning"
        entry = {
            "file": (file_ or "").strip(),
            "line": int(line_s) if line_s else 0,
            "severity": sev,
            "message": message.strip(),
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
    """Compile with vlog -sv, simulate with vsim -c."""
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
    vlog = resolve("questa")  # binary resolved via _BINARY map: questa → vsim
    # resolve("questa") gives vsim path; derive vlog from same dir
    vsim = vlog
    if vsim:
        vsim_path = Path(vsim)
        vlog_bin = str(vsim_path.parent / "vlog")
        if not Path(vlog_bin).exists():
            vlog_bin = "vlog"
    else:
        return _not_found()

    top_mod = top or Path(testbench).stem
    # vlog compiles in a temp dir, where a relative source path no longer
    # points at the caller's file.
    sources = [str(Path(f).resolve()) for f in (testbench, dut, *extra_sources)]

    with tempfile.TemporaryDirectory(prefix="silica_questa_") as tmpdir:
        # Create work library
        lp = subprocess.run(
            ["vlib", "work"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
        )
        if lp.returncode != 0:
            detail = (lp.stderr or lp.stdout).strip()
            return {
                "exit_code": lp.returncode,
                "errors": [_generic_error(dut, f"vlib failed to create work library: {detail}")],
                "warnings": [],
                "raw_stdout": lp.stdout,
                "raw_stderr": lp.stderr,
                "trace_vcd": None,
            }

        compile_cmd = [vlog_bin, "-sv", *sources]
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
                "errors": compile_errors or [_generic_error(dut, "vlog compilation failed")],
                "warnings": compile_warnings,
                "raw_stdout": cp.stdout,
                "raw_stderr": cp.stderr,
                "trace_vcd": None,
            }

        # Persistent trace dir, created only after a successful compile so
        # failed runs don't leak dirs.
        trace_dir = tempfile.mkdtemp(prefix="silica_trace_") if trace else None

        do_cmds = []
        if trace:
            vcd_path = str(Path(trace_dir) / "dump.vcd") if trace_dir else "dump.vcd"
            do_cmds += [
                f"vcd file {vcd_path}",
                "vcd add -r /*",
            ]
        do_cmds += ["run -all", "quit"]
        do_script = "; ".join(do_cmds)

        # Simulate in the DUT's directory, as the other simulators do, so
        # relative paths in the testbench ($readmemh) resolve from there. The
        # work library, waveform database and transcript stay in the temp dir.
        # Unverified: no Questa install was available to confirm that -lib
        # takes a library directory path; if it doesn't, vsim won't find the
        # top unit and the run fails with a vsim error.
        tmp = Path(tmpdir)
        sim_cmd = [
            vsim, "-c",
            "-lib", str(tmp / "work"),
            "-wlf", str(tmp / "vsim.wlf"),
            "-l", str(tmp / "transcript"),
            "-do", do_script,
            top_mod,
        ]
        rp = subprocess.run(
            sim_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(dut).parent),
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


def _timeout_result(file: str, timeout: int) -> dict:
    return {
        "exit_code": -1,
        "errors": [_generic_error(file, f"questa timed out after {timeout}s")],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }


def _not_found() -> dict:
    return {
        "exit_code": -1,
        "errors": [_generic_error(
            "", "vsim/vlog not found. Questa requires a Siemens EDA license.")],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }
