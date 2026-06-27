"""Config-aware tool selection for auto dispatch."""

import shutil

from silica import config as cfg
from silica import oss_cad_suite

# Maps registry tool names to the binary (or binaries) that shutil.which
# should probe. A list means "try each in order" — commercial tools ship
# under different invocation names across versions and product variants.
_BINARY: dict[str, str | list[str]] = {
    "verilator": "verilator",
    "iverilog": "iverilog",
    "vcs": "vcs",
    "questa": ["vsim", "qrun"],
    "xcelium": ["xrun", "irun"],
    "yosys": "yosys",
    "vivado": "vivado",
    "quartus": "quartus_sh",
    "dc_shell": ["dc_shell", "dc_shell-t"],
    "sby": "sby",
    "jaspergold": ["jg", "jaspergold"],
    "vc_formal": ["vcf", "vc_static_shell"],
    "verible-verilog-lint": "verible-verilog-lint",
    "svlint": "svlint",
    "spyglass": ["spyglass", "sg_shell", "vc_static_shell"],
    "surfer": "surfer",
    "gtkwave": "gtkwave",
    "verdi": "verdi",
}


def _binaries(name: str) -> list[str]:
    """Return the candidate binary names for a registry tool, in priority order."""
    val = _BINARY.get(name, name)
    return val if isinstance(val, list) else [val]


def resolve(name: str) -> str | None:
    """Return the location of the first matching binary for a tool, or None.

    Maps the registry name (e.g. ``"questa"``) to its real binary (``vsim``)
    before probing — use this for detection instead of ``shutil.which(name)``.
    Checks global PATH first, then a managed/detected OSS CAD Suite install for
    tools the suite bundles.
    """
    for binary in _binaries(name):
        path = shutil.which(binary)
        if path:
            return path
    # Fall back to an OSS CAD Suite install (not necessarily on PATH).
    if name in oss_cad_suite.BUNDLED:
        for binary in _binaries(name):
            path = oss_cad_suite.binary_path(binary)
            if path:
                return path
    return None

# Fallback priority when config is missing entirely, keyed by category
_FALLBACK: dict[str, list[str]] = {
    "simulation": ["verilator", "iverilog"],
    "synthesis": ["yosys"],
    "formal": ["sby"],
    "lint": ["verible-verilog-lint", "verilator"],
    "waveform": ["surfer", "gtkwave"],
}


def pick(category: str) -> str | None:
    """Return the first available tool name for the given category.

    Respects config priority order when ~/.silica/config.toml exists;
    falls back to hardcoded defaults otherwise. Returns None if nothing
    on PATH matches.
    """
    data = cfg.load()
    tools_cfg = data.get("tools", {}).get(category, {})
    priority = tools_cfg.get("priority") or tools_cfg.get("enabled") or []

    if not priority:
        priority = _FALLBACK.get(category, [])

    for name in priority:
        if resolve(name):
            return name

    return None


def is_enabled(category: str, name: str) -> bool:
    """Return True if the tool is in the enabled list for its category."""
    data = cfg.load()
    enabled = data.get("tools", {}).get(category, {}).get("enabled", [])
    if not enabled:
        return True  # no config — allow anything
    return name in enabled
