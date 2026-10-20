"""nextpnr adapter — place and route for FPGA architectures."""

import os
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
    "xilinx":   "nextpnr-xilinx",
}

_OUT_FLAG = {
    "ice40":    "--asc",
    "ecp5":     "--textcfg",
    "nexus":    "--fasm",
    "machxo2":  "--textcfg",
    "generic":  "--json",
    "xilinx":   "--fasm",
}

_OUT_EXT = {
    "ice40":    ".bin",
    "ecp5":     ".bit",
    "nexus":    ".fasm",
    "machxo2":  ".textcfg",
    "generic":  ".json",
    "xilinx":   ".bit",
}

# Architectures whose nextpnr output is packed into a bitstream afterwards:
# arch -> extension of nextpnr's intermediate file.
_INTERMEDIATE_EXT = {
    "ice40":    ".asc",
    "ecp5":     ".textcfg",
    "xilinx":   ".fasm",
}

# Lattice packers from OSS CAD Suite: icestorm's icepack, Trellis's ecppack.
_LATTICE_PACKER = {
    "ice40":    "icepack",
    "ecp5":     "ecppack",
}

_CONSTRAINT_FLAG = {
    "ice40":    "--pcf",
    "ecp5":     "--lpf",
    "nexus":    "--pdc",
    "machxo2":  "--lpf",
    "xilinx":   "--xdc",
}

# nextpnr-ecp5 has no --device option; it takes one flag per device, e.g.
# --25k for LFE5U-25F or --um5g-85k for LFE5UM5G-85F.
_ECP5_PART_RE = re.compile(r"^LFE5(U|UM|UM5G)-(12|25|45|85)F(?:-([678]))?", re.IGNORECASE)
_ECP5_FLAG_RE = re.compile(r"^(?:um-|um5g-)?(?:12|25|45|85)k$")
_ECP5_FAMILY_FLAG = {"U": "", "UM": "um-", "UM5G": "um5g-"}

# Xilinx 7-series part prefix -> prjxray-db family directory.
_XC7_FAMILY = {
    "xc7a": "artix7",
    "xc7k": "kintex7",
    "xc7s": "spartan7",
    "xc7z": "zynq7",
    "xc7v": "virtex7",
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
        arch: FPGA architecture — "ice40" | "ecp5" | "nexus" | "machxo2" |
              "generic" | "xilinx".
        device: Device variant, e.g. "hx8k" (ice40), "LFE5U-45F" (ecp5), or a
                full part with speed grade for xilinx, e.g. "xc7a100tcsg324-1".
        package: Package code, e.g. "ct256" (ice40), "CABGA381" (ecp5). Optional.
        constraint: Path to constraint file (.pcf for ice40, .lpf for ecp5,
                    .xdc for xilinx).
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

    chipdb = None
    if arch == "xilinx":
        chipdb = _xilinx_chipdb(device)
        if chipdb is None:
            return _error_result(arch, device, (
                f"No nextpnr-xilinx chip database found for '{device}'. Pass "
                "the .bin path as device, or put <part without speed "
                "grade>.bin (e.g. xc7a100tcsg324.bin) in a directory named by "
                "NEXTPNR_XILINX_CHIPDB_DIR or <FAMILY>_CHIPDB "
                "(e.g. ARTIX7_CHIPDB), as the openXC7 toolchain does."
            ))

    ecp5_args = None
    if arch == "ecp5":
        ecp5_args = _ecp5_device_args(device)
        if ecp5_args is None:
            return _error_result(arch, device, (
                f"Unknown ECP5 device '{device}'. Use a part such as LFE5U-25F, "
                "LFE5UM-45F or LFE5UM5G-85F (a speed grade suffix like "
                "LFE5U-25F-6 is passed as --speed), or a nextpnr-ecp5 device "
                "flag such as 25k or um5g-85k."
            ))

    workdir = Path(tempfile.mkdtemp(prefix="silica_nextpnr_"))
    out_ext = _OUT_EXT.get(arch, ".out")
    out_path = Path(output).resolve() if output else workdir / f"out{out_ext}"
    # nextpnr writes FASM (xilinx) or a text config (ice40/ecp5); fpga-as,
    # icepack or ecppack turns it into the bitstream at out_path. An output
    # named like the intermediate file keeps it there, with the bitstream
    # beside it.
    pnr_out = out_path
    mid_ext = _INTERMEDIATE_EXT.get(arch)
    if mid_ext:
        pnr_out = workdir / f"out{mid_ext}"
        if out_path.suffix == mid_ext:
            pnr_out, out_path = out_path, out_path.with_suffix(out_ext)

    cmd = [binary, "--json", str(netlist_path)]

    if arch == "xilinx":
        cmd += ["--chipdb", str(chipdb)]
    elif arch == "ice40":
        # ice40 uses named device flags: --hx8k, --up5k, etc.
        cmd.append(f"--{device}")
        if package:
            cmd += ["--package", package]
    elif arch == "ecp5":
        cmd += ecp5_args
        if package:
            cmd += ["--package", package]
    else:
        cmd += ["--device", device]
        if package:
            cmd += ["--package", package]

    if constraint:
        flag = _CONSTRAINT_FLAG.get(arch, "--pre-place")
        cmd += [flag, str(Path(constraint).resolve())]

    cmd += [_OUT_FLAG.get(arch, "--json"), str(pnr_out)]

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
    asm_warning = None
    if mid_ext and cp.returncode == 0 and pnr_out.exists():
        if arch == "xilinx":
            asm_warning, asm_log = _assemble_xc7(pnr_out, device, out_path, timeout)
        else:
            asm_warning, asm_log = _pack_lattice(arch, pnr_out, out_path, timeout)
        raw += asm_log
        if asm_warning:
            out_path = pnr_out
    timing = _parse_timing(raw)
    util = _parse_utilization(raw)
    warnings = [{"message": m.group(1).strip()} for m in _WARNING_RE.finditer(raw)]
    errors = [{"message": m.group(1).strip()} for m in _ERROR_RE.finditer(raw)]

    if cp.returncode != 0 and not errors:
        errors.append({"message": "nextpnr place-and-route failed — see raw_output"})
    if asm_warning:
        warnings.append({"message": asm_warning})

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


def _xilinx_chipdb(device: str) -> Path | None:
    """Locate the nextpnr-xilinx chip database for a 7-series part.

    ``device`` may be the database path itself. Otherwise it is a part such as
    "xc7a100tcsg324-1" and ``<part without speed grade>.bin`` is looked up in
    the directories openXC7 uses: NEXTPNR_XILINX_CHIPDB_DIR (set by its Nix
    shell) and <FAMILY>_CHIPDB (its Makefiles, e.g. ARTIX7_CHIPDB)."""
    if device.endswith(".bin"):
        path = Path(device).expanduser()
        return path if path.is_file() else None
    dbpart = re.sub(r"-\d\w*$", "", device.lower())
    dirs = os.environ.get("NEXTPNR_XILINX_CHIPDB_DIR", "").split(os.pathsep)
    family = _XC7_FAMILY.get(dbpart[:4])
    if family:
        dirs.append(os.environ.get(f"{family.upper()}_CHIPDB", ""))
    for d in dirs:
        if d and (Path(d) / f"{dbpart}.bin").is_file():
            return Path(d) / f"{dbpart}.bin"
    return None


def _ecp5_device_args(device: str) -> list[str] | None:
    """nextpnr-ecp5 arguments for a part ("LFE5U-25F", "LFE5UM5G-85F-8") or a
    device flag name ("25k", "um5g-85k"); None if neither."""
    m = _ECP5_PART_RE.match(device.strip())
    if m:
        args = [f"--{_ECP5_FAMILY_FLAG[m.group(1).upper()]}{m.group(2)}k"]
        if m.group(3):
            args += ["--speed", m.group(3)]
        return args
    flag = device.strip().lower().lstrip("-")
    return [f"--{flag}"] if _ECP5_FLAG_RE.match(flag) else None


def _assemble_xc7(fasm: Path, part: str, out_path: Path, timeout: int) -> tuple[str | None, str]:
    """Assemble a nextpnr-xilinx FASM file into a .bit with openXC7's fpga-as.

    Returns (warning, log). The warning is None when out_path was written;
    otherwise it says why the FASM is the final output."""
    family = _XC7_FAMILY.get(part.lower()[:4])
    fpga_as = oss_cad_suite.which("fpga-as")
    db_root = os.environ.get("PRJXRAY_DB_DIR")
    if not fpga_as or not db_root or not family or not re.search(r"-\d", part):
        return (
            "Output is FASM, not a bitstream: assembling a .bit needs openXC7's "
            "fpga-as on PATH, PRJXRAY_DB_DIR set to the prjxray-db root, and "
            "device given as a full part with speed grade (e.g. xc7a100tcsg324-1).",
            "",
        )
    try:
        with fasm.open("rb") as src, out_path.open("wb") as dst:
            cp = subprocess.run(
                [fpga_as, f"--prjxray_db_path={Path(db_root) / family}", "--part", part],
                stdin=src,
                stdout=dst,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        out_path.unlink(missing_ok=True)
        return f"fpga-as timed out after {timeout}s; output is FASM.", ""
    log = cp.stderr.decode(errors="replace")
    if cp.returncode != 0:
        # A truncated .bit would still program and report success.
        out_path.unlink(missing_ok=True)
        return f"fpga-as failed with exit code {cp.returncode}; output is FASM.", log
    return None, log


def _pack_lattice(arch: str, text_cfg: Path, out_path: Path,
                  timeout: int) -> tuple[str | None, str]:
    """Pack nextpnr's iCE40 .asc or ECP5 .textcfg into a bitstream with
    icepack or ecppack.

    Returns (warning, log). The warning is None when out_path was written;
    otherwise it says why the text config is the final output."""
    packer = _LATTICE_PACKER[arch]
    binary = oss_cad_suite.which(packer)
    if not binary:
        return (
            f"Output is nextpnr's {text_cfg.suffix} text config, not a bitstream: "
            f"packing it needs {packer} on PATH (it ships with OSS CAD Suite: "
            "https://github.com/YosysHQ/oss-cad-suite-build/releases).",
            "",
        )
    try:
        cp = subprocess.run(
            [binary, str(text_cfg), str(out_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        out_path.unlink(missing_ok=True)
        return f"{packer} timed out after {timeout}s; output is the text config.", ""
    log = cp.stdout + cp.stderr
    if cp.returncode != 0:
        out_path.unlink(missing_ok=True)
        return f"{packer} failed with exit code {cp.returncode}; output is the text config.", log
    return None, log


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
    if arch == "xilinx":
        hint = ("nextpnr-xilinx is not in OSS CAD Suite; install the openXC7 "
                "toolchain: https://github.com/openXC7/toolchain-nix")
    else:
        hint = install_hint("nextpnr")
    return _error_result(arch, "unknown", f"{binary_name} not found.\n{hint}")
