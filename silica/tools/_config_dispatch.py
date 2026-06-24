"""Config-aware tool selection for auto dispatch."""

import shutil

from silica import config as cfg

# Maps registry tool names to the binary that shutil.which should probe
_BINARY: dict[str, str] = {
    "verilator": "verilator",
    "iverilog": "iverilog",
    "vcs": "vcs",
    "questa": "vsim",
    "xcelium": "xrun",
    "yosys": "yosys",
    "vivado": "vivado",
    "quartus": "quartus_sh",
    "dc_shell": "dc_shell",
    "sby": "sby",
    "jaspergold": "jg",
    "vc_formal": "vcf",
    "verible-verilog-lint": "verible-verilog-lint",
    "svlint": "svlint",
    "spyglass": "spyglass",
    "surfer": "surfer",
    "gtkwave": "gtkwave",
    "verdi": "verdi",
}

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
        binary = _BINARY.get(name, name)
        if shutil.which(binary):
            return name

    return None


def is_enabled(category: str, name: str) -> bool:
    """Return True if the tool is in the enabled list for its category."""
    data = cfg.load()
    enabled = data.get("tools", {}).get(category, {}).get("enabled", [])
    if not enabled:
        return True  # no config — allow anything
    return name in enabled
