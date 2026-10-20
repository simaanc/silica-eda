"""Environment report for the doctor tool: silica's version and the EDA tools it can use.

Open-source tools are found the way the adapters find them (PATH, then an OSS
CAD Suite install) and asked for their version. Commercial tools are only
looked up, never run, since starting one can check out a license. Each tool
that is missing or too old gets a concrete fix.
"""

import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from silica import __version__, oss_cad_suite
from silica.adapters._hints import install_hint
from silica.tools_registry import TOOLS

PYPI_URL = "https://pypi.org/pypi/silica-eda/json"

_OPENXC7_FIX = ("Install the openXC7 toolchain (it is not in OSS CAD Suite): "
                "https://github.com/openXC7/toolchain-nix")


class _Check:
    def __init__(self, name, binary, version_args, used_by, hint=None,
                 min_version=None, min_reason="", fix=None):
        self.name = name
        self.binary = binary
        self.version_args = version_args  # None: the tool can't report its version
        self.used_by = used_by
        self.hint = hint or name          # key into adapters._hints
        self.min_version = min_version
        self.min_reason = min_reason
        self.fix = fix                    # overrides the install hint


# Open-source tools, in workflow order.
CHECKS = [
    _Check("verilator", "verilator", ["--version"], "lint, run_simulation, read_coverage",
           min_version="5.002", min_reason="silica builds simulations with --binary, "
                                           "added in Verilator 5.002"),
    _Check("verible-verilog-lint", "verible-verilog-lint", ["--version"], "lint"),
    _Check("verible-verilog-format", "verible-verilog-format", ["--version"], "format_rtl"),
    _Check("svlint", "svlint", ["--version"], "lint"),
    _Check("iverilog", "iverilog", ["-V"], "run_simulation, run_cocotb"),
    _Check("ghdl", "ghdl", ["--version"], "run_simulation (VHDL)"),
    _Check("sby", "sby", ["--version"], "run_formal"),
    _Check("eqy", "eqy", ["--version"], "run_formal (equivalence)"),
    _Check("yosys", "yosys", ["-V"], "synthesize"),
    _Check("nextpnr-ice40", "nextpnr-ice40", ["--version"], "run_place_route (ice40)",
           hint="nextpnr"),
    _Check("nextpnr-ecp5", "nextpnr-ecp5", ["--version"], "run_place_route (ecp5)",
           hint="nextpnr"),
    _Check("nextpnr-nexus", "nextpnr-nexus", ["--version"], "run_place_route (nexus)",
           hint="nextpnr"),
    _Check("nextpnr-machxo2", "nextpnr-machxo2", ["--version"], "run_place_route (machxo2)",
           hint="nextpnr"),
    _Check("nextpnr-xilinx", "nextpnr-xilinx", None, "run_place_route (xilinx)",
           fix=_OPENXC7_FIX),
    _Check("fpga-as", "fpga-as", None, "run_place_route (xilinx .bit assembly)",
           fix=_OPENXC7_FIX),
    _Check("openFPGALoader", "openFPGALoader", ["--Version"], "program_device",
           hint="openfpgaloader"),
    _Check("surfer", "surfer", ["--version"], "launch_waveform"),
    _Check("gtkwave", "gtkwave", ["--version"], "launch_waveform"),
]

# Python packages behind optional extras: (distribution, extra, tool, import fix).
EXTRAS = [
    ("cocotb", "cocotb", "run_cocotb"),
    ("pyserial", "serial", "capture_serial"),
]

_VERSION_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?(?:[-+][\w.+-]*)?)")


def parse_version(text: str) -> str | None:
    """First version-looking token in a tool's --version output."""
    m = _VERSION_RE.search(text)
    return m.group(1) if m else None


def version_key(version: str) -> tuple[int, ...]:
    """Numeric MAJOR.MINOR.PATCH prefix for comparisons ("5.053" -> (5, 53, 0))."""
    nums = [int(n) for n in re.findall(r"\d+", version.split("-")[0].split("+")[0])[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def _probe(check: _Check, timeout: float) -> dict:
    path = oss_cad_suite.which(check.binary)
    entry = {
        "name": check.name,
        "used_by": check.used_by,
        "found": path is not None,
        "path": path,
        "version": None,
        "min_version": check.min_version,
    }
    if not path:
        entry["status"] = "missing"
        entry["fix"] = check.fix or install_hint(check.hint)
        return entry
    if check.version_args is None:
        entry["status"] = "found"
        entry["note"] = "this tool doesn't report a version"
        return entry
    try:
        cp = subprocess.run([path, *check.version_args], capture_output=True, text=True,
                            timeout=timeout, stdin=subprocess.DEVNULL,
                            env=oss_cad_suite.env_with_suite())
        entry["version"] = parse_version(cp.stdout + cp.stderr)
    except (subprocess.TimeoutExpired, OSError) as exc:
        entry["note"] = f"version query failed: {exc}"
    if entry["version"] is None:
        entry["status"] = "found"
        entry.setdefault("note", "couldn't read a version from its output")
    elif check.min_version and version_key(entry["version"]) < version_key(check.min_version):
        entry["status"] = "outdated"
        entry["fix"] = (f"{check.name} {entry['version']} is older than {check.min_version} "
                        f"({check.min_reason}). Upgrade it:\n"
                        f"{check.fix or install_hint(check.hint)}")
    else:
        entry["status"] = "ok"
    return entry


def _commercial() -> list[dict]:
    from silica.detect import resolve

    found = []
    for name, info in TOOLS.items():
        if info.get("license") != "commercial":
            continue
        path = resolve(name)
        found.append({"name": name, "category": info["category"],
                      "found": path is not None, "path": path})
    return found


def _extras() -> list[dict]:
    out = []
    for dist, extra, tool in EXTRAS:
        try:
            version = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            version = None
        entry = {"name": dist, "extra": extra, "used_by": tool,
                 "installed": version is not None, "version": version}
        if version is None:
            entry["fix"] = (f'pip install "silica-eda[{extra}]", or for a uvx launch: '
                            f"uvx --with {dist} silica-eda@latest")
        out.append(entry)
    return out


def check_for_update(timeout: float = 3.0) -> dict:
    """Ask PyPI for the newest silica-eda; never raises."""
    if os.environ.get("SILICA_NO_UPDATE_CHECK"):
        return {"latest": None, "update_available": None, "update_check": "disabled"}
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=timeout) as resp:
            latest = json.load(resp)["info"]["version"]
    except Exception as exc:  # offline, DNS, proxy, bad JSON: report and carry on
        return {"latest": None, "update_available": None,
                "update_check": f"unavailable ({type(exc).__name__})"}
    result = {"latest": latest, "update_check": "ok"}
    if not re.fullmatch(r"\d+\.\d+\.\d+", __version__):
        result["update_available"] = None  # a dev or pre-release build
        return result
    result["update_available"] = version_key(latest) > version_key(__version__)
    if result["update_available"]:
        result["fix"] = (f"silica-eda {latest} is available (running {__version__}). "
                         "Clients that launch `uvx silica-eda@latest` get it on their "
                         "next start; for a pip install run: pip install -U silica-eda")
    return result


def report(check_updates: bool = True, timeout: float = 10.0) -> dict:
    with ThreadPoolExecutor(max_workers=8) as pool:
        tools = list(pool.map(lambda c: _probe(c, timeout), CHECKS))
    silica_info = {"version": __version__}
    silica_info.update(check_for_update() if check_updates
                       else {"latest": None, "update_available": None,
                             "update_check": "skipped"})
    suite = oss_cad_suite.find_root()
    return {
        "silica": silica_info,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "executable": sys.executable,
        "oss_cad_suite": str(suite) if suite else None,
        "tools": tools,
        "python_extras": _extras(),
        "commercial": _commercial(),
        "summary": {
            "ok": [t["name"] for t in tools if t["status"] in ("ok", "found")],
            "missing": [t["name"] for t in tools if t["status"] == "missing"],
            "outdated": [t["name"] for t in tools if t["status"] == "outdated"],
        },
    }
