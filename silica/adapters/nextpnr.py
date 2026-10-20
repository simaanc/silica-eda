"""nextpnr adapter — place and route for FPGA architectures."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica import oss_cad_suite
from silica.adapters._hints import install_hint

_FREQ_RE = re.compile(
    r"Max frequency for clock '([^']+)':\s*([\d.]+)\s*MHz\s*\((PASS|FAIL)"
)
_UTIL_RE = re.compile(
    r"^\s*Info:\s+([\w_]+):\s+(\d+)/\s*(\d+)\s+(\d+)%",
    re.MULTILINE,
)
_WARNING_RE = re.compile(r"^\s*Warning:\s*(.+)$", re.MULTILINE)
_ERROR_RE = re.compile(r"^\s*ERROR:\s*(.+)$", re.MULTILINE)

_ARCH_BINARY = {
    "ice40":    "nextpnr-ice40",
    "ecp5":     "nextpnr-ecp5",
    "nexus":    "nextpnr-nexus",
    "machxo2":  "nextpnr-machxo2",
    "generic":  "nextpnr-generic",
}

_OUT_FLAG = {
    "ice40":    "--asc",
    "ecp5":     "--textcfg",
    "nexus":    "--fasm",
    "machxo2":  "--textcfg",
    "generic":  "--json",
}

_OUT_EXT = {
    "ice40":    ".asc",
    "ecp5":     ".textcfg",
    "nexus":    ".fasm",
    "machxo2":  ".textcfg",
    "generic":  ".json",
}

_CONSTRAINT_FLAG = {
    "ice40":    "--pcf",
    "ecp5":     "--lpf",
    "nexus":    "--pdc",
    "machxo2":  "--lpf",
}


def run(
    netlist: str,
    arch: str = "ice40",
    device: str = "hx8k",
    package: str | None = None,
    constraint: str | None = None,
    output: str | None = None,
    freq: float | None = None,
    timeout: int = 120,
) -> dict:
    """Place and route a Yosys JSON netlist with nextpnr.

    Args:
        netlist: Path to Yosys JSON netlist (from synth_<arch> -json ...).
        arch: FPGA architecture — "ice40" | "ecp5" | "nexus" | "machxo2" | "generic".
        device: Device variant, e.g. "hx8k" (ice40), "LFE5U-45F" (ecp5).
        package: Package code, e.g. "ct256" (ice40), "CABGA381" (ecp5). Optional.
        constraint: Path to constraint file (.pcf for ice40, .lpf for ecp5).
        output: Output file path. Written to a persistent temp dir if omitted.
        freq: Target clock frequency in MHz for timing checks.
        timeout: Seconds before killing nextpnr.
    """
    binary = oss_cad_suite.which(_ARCH_BINARY.get(arch, f"nextpnr-{arch}"))
    if not binary:
        return _not_found(arch)

    netlist_path = Path(netlist).resolve()
    if not netlist_path.exists():
        return _error_result(arch, device, f"Netlist not found: {netlist}")

    workdir = Path(tempfile.mkdtemp(prefix="silica_nextpnr_"))
    out_ext = _OUT_EXT.get(arch, ".out")
    out_path = Path(output).resolve() if output else workdir / f"out{out_ext}"

    cmd = [binary, "--json", str(netlist_path)]

    if arch == "ice40":
        # ice40 uses named device flags: --hx8k, --up5k, etc.
        cmd.append(f"--{device}")
        if package:
            cmd += ["--package", package]
    else:
        cmd += ["--device", device]
        if package:
            cmd += ["--package", package]

    if constraint:
        flag = _CONSTRAINT_FLAG.get(arch, "--pre-place")
        cmd += [flag, str(Path(constraint).resolve())]

    cmd += [_OUT_FLAG.get(arch, "--json"), str(out_path)]

    if freq is not None:
        cmd += ["--freq", str(freq)]

    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        return _error_result(arch, device, f"nextpnr timed out after {timeout}s")

    raw = cp.stdout + cp.stderr
    timing = _parse_timing(raw)
    util = _parse_utilization(raw)
    warnings = [{"message": m.group(1).strip()} for m in _WARNING_RE.finditer(raw)]
    errors = [{"message": m.group(1).strip()} for m in _ERROR_RE.finditer(raw)]

    if cp.returncode != 0 and not errors:
        errors.append({"message": "nextpnr place-and-route failed — see raw_output"})

    # rc==0 with nothing parsed is indistinguishable from an empty design;
    # flag it so all-zero metrics aren't read as a real result.
    if cp.returncode == 0 and not util and not timing["clocks"]:
        warnings.append({"message": (
            "No utilization or timing figures found in nextpnr output; "
            "the report format may be unsupported — check raw_output."
        )})

    return {
        "tool": _ARCH_BINARY.get(arch, f"nextpnr-{arch}"),
        "target": f"{device}-{package}" if package else device,
        "exit_code": cp.returncode,
        "timing_summary": timing,
        "utilization": util,
        "output": str(out_path) if out_path.exists() else None,
        "workdir": str(workdir),
        "warnings": warnings,
        "errors": errors,
        "raw_output": raw,
    }


def _parse_timing(raw: str) -> dict:
    # nextpnr reports each clock after placement and again after routing;
    # the last report is the routed result, so it replaces earlier ones.
    by_clock: dict[str, dict] = {}
    for m in _FREQ_RE.finditer(raw):
        by_clock[m.group(1)] = {
            "clock": m.group(1),
            "max_freq_mhz": float(m.group(2)),
            "pass": m.group(3) == "PASS",
        }
    clocks = list(by_clock.values())
    failing = sum(1 for c in clocks if not c["pass"])
    return {"clocks": clocks, "wns": 0.0, "failing_endpoints": failing}


def _parse_utilization(raw: str) -> dict:
    cells: dict[str, dict] = {}
    for m in _UTIL_RE.finditer(raw):
        name = m.group(1)
        cells[name] = {
            "used": int(m.group(2)),
            "total": int(m.group(3)),
            "pct": int(m.group(4)),
        }
    return cells


def _error_result(arch: str, device: str, message: str) -> dict:
    return {
        "tool": _ARCH_BINARY.get(arch, f"nextpnr-{arch}"),
        "target": device,
        "exit_code": -1,
        "timing_summary": {"clocks": [], "wns": 0.0, "failing_endpoints": 0},
        "utilization": {},
        "output": None,
        "workdir": "",
        "warnings": [],
        "errors": [{"message": message}],
        "raw_output": "",
    }


def _not_found(arch: str) -> dict:
    binary_name = _ARCH_BINARY.get(arch, f"nextpnr-{arch}")
    return _error_result(
        arch, "unknown",
        f"{binary_name} not found.\n{install_hint('nextpnr')}",
    )
