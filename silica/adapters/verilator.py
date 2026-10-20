"""Verilator adapter — compile-and-simulate using --binary (Verilator 5+)."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from silica import oss_cad_suite
from silica.adapters import _sim_output
from silica.adapters._hints import install_hint


def _find_make() -> str | None:
    """Return the first available make-compatible tool, searching the OSS CAD Suite PATH too."""
    suite_path = oss_cad_suite.env_with_suite().get("PATH", "")
    for tool in ("make", "gmake", "mingw32-make"):
        if shutil.which(tool) or shutil.which(tool, path=suite_path):
            return tool
    return None


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
    extra_sources: list[str] | None = None,
    coverage: bool = False,
) -> dict:
    """Compile and simulate with Verilator (--binary mode, Verilator 5+).

    Falls back to lint-only mode if --binary is unsupported.
    When trace=True, writes dump.vcd to a persistent temp directory and
    returns its path as trace_vcd in the result.
    When coverage=True, compiles with --coverage; the simulation writes
    coverage.dat, whose path is returned as coverage_dat (feed it to
    read_coverage).

    extra_sources: additional design files (submodules, packages) compiled
    alongside dut and testbench.
    """
    try:
        return _run(dut, testbench, top, timeout, trace, extra_sources or [],
                    coverage)
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
    coverage: bool,
) -> dict:
    binary = _find_verilator()
    if not binary:
        return _not_found()

    env = oss_cad_suite.env_with_suite()
    make_tool = _find_make()

    if top is None:
        # Infer top from testbench filename stem
        top = Path(testbench).stem

    with tempfile.TemporaryDirectory(prefix="silica_veri_") as tmpdir:
        obj_dir = Path(tmpdir) / "obj_dir"
        sim_bin = Path(tmpdir) / f"V{top}"

        compile_cmd = [
            binary,
            "--binary",
            "--build",
            "-Wall",
            # Report lint warnings but don't let them stop the simulation;
            # lint_only is the strict path.
            "-Wno-fatal",
            "-Wno-TIMESCALEMOD",
            "-Wno-STMTDLY",
            "-Wno-PROCASSINIT",
            "--top-module", top,
            "--Mdir", str(obj_dir),
            "-o", str(sim_bin),
            dut,
            testbench,
            *extra_sources,
        ]
        if make_tool and make_tool != "make":
            compile_cmd.extend(["--make", make_tool])
        if trace:
            compile_cmd.append("--trace")
        if coverage:
            compile_cmd.append("--coverage")

        cp = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        errors, warnings = _parse_output(cp.stderr)

        if cp.returncode != 0:
            if not errors:
                errors.append({
                    "file": dut,
                    "line": 0,
                    "severity": "error",
                    "message": (f"Verilator build failed with exit code "
                                f"{cp.returncode} — see raw_stderr"),
                })
            result: dict = {
                "exit_code": cp.returncode,
                "errors": errors,
                "warnings": warnings,
                "raw_stdout": cp.stdout,
                "raw_stderr": cp.stderr,
                "trace_vcd": None,
                "coverage_dat": None,
            }
            return result

        # When tracing or collecting coverage, keep a persistent dir so the VCD
        # / coverage.dat survive after we return. Created only after a
        # successful compile so failed runs don't leak dirs.
        out_dir = (tempfile.mkdtemp(prefix="silica_trace_")
                   if (trace or coverage) else None)

        # Run in the DUT's directory either way, so relative paths in the
        # testbench ($readmemh) don't depend on tracing or coverage. VCDs move
        # to out_dir afterwards; coverage.dat is written there directly.
        sim_cwd = str(Path(dut).parent)
        sim_cmd = [str(sim_bin)]
        if coverage:
            sim_cmd.append(f"+verilator+coverage+file+{Path(out_dir) / 'coverage.dat'}")
        vcds_before = _sim_output.snapshot(sim_cwd) if trace else {}
        rp = subprocess.run(
            sim_cmd,
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
        coverage_dat = None
        if out_dir:
            if trace:
                vcds = _sim_output.move_written(sim_cwd, vcds_before, out_dir)
                trace_vcd = str(vcds[0]) if vcds else None
            if coverage:
                dat = Path(out_dir) / "coverage.dat"
                coverage_dat = str(dat) if dat.exists() else None

        return {
            "exit_code": rp.returncode,
            "errors": all_errors,
            "warnings": all_warnings,
            "raw_stdout": cp.stdout + rp.stdout,
            "raw_stderr": cp.stderr + rp.stderr,
            "trace_vcd": trace_vcd,
            "coverage_dat": coverage_dat,
        }


def coverage_info(dat_file: str, timeout: int = 30) -> dict:
    """Convert a Verilator coverage.dat into lcov ``.info`` text.

    Shells out to verilator_coverage (ships with Verilator) with --write-info.
    Returns {"info": <lcov text>} on success or {"error": str}. The lcov info
    is line-oriented (SF/DA/... records) and parsed by the read_coverage tool.
    """
    tool = oss_cad_suite.which("verilator_coverage") or shutil.which("verilator_coverage")
    if not tool:
        return {"error": (
            "verilator_coverage not found — it ships with Verilator. "
            "Install Verilator / the OSS CAD Suite."
        )}
    fd, info = tempfile.mkstemp(prefix="silica_cov_", suffix=".info")
    os.close(fd)
    try:
        cp = subprocess.run(
            [tool, "--write-info", info, dat_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        Path(info).unlink(missing_ok=True)
        return {"error": f"verilator_coverage timed out after {timeout}s"}
    if cp.returncode != 0:
        Path(info).unlink(missing_ok=True)
        detail = (cp.stderr or cp.stdout).strip()
        return {"error": f"verilator_coverage failed: {detail}"}
    try:
        text = Path(info).read_text(encoding="utf-8", errors="replace")
    finally:
        Path(info).unlink(missing_ok=True)
    return {"info": text}


def lint_only(file: str, timeout: int = 30, extra_files: list[str] | None = None) -> dict:
    """Run verilator --lint-only for a quick syntax/semantic check.

    extra_files are elaborated together with file, so a top-level module can
    find its submodules."""
    binary = _find_verilator()
    if not binary:
        return _not_found()

    try:
        cp = subprocess.run(
            [binary, "--lint-only", "-Wall", "-Wno-TIMESCALEMOD", file,
             *(extra_files or [])],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "errors": [{"file": file, "line": 0, "severity": "error",
                        "message": f"verilator timed out after {timeout}s"}],
            "warnings": [],
            "raw_stdout": "",
            "raw_stderr": "",
        }
    errors, warnings = _parse_output(cp.stderr)
    return {
        "exit_code": cp.returncode,
        "errors": errors,
        "warnings": warnings,
        "raw_stdout": cp.stdout,
        "raw_stderr": cp.stderr,
    }


def _timeout_result(file: str, timeout: int) -> dict:
    return {
        "exit_code": -1,
        "errors": [{"file": file, "line": 0, "severity": "error",
                    "message": f"verilator timed out after {timeout}s"}],
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
            "message": f"verilator not found.\n{install_hint('verilator')}",
        }],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
    }
