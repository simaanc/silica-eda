"""Config-aware tool selection for auto dispatch."""

from silica import config as cfg
from silica.detect import resolve

# Fallback priority when config is missing entirely, keyed by category.
# Open-source tools listed first; commercial tools are detected if on PATH.
_FALLBACK: dict[str, list[str]] = {
    "simulation":  ["verilator", "iverilog", "ghdl", "vcs", "questa", "xcelium"],
    "synthesis":   ["yosys", "vivado", "quartus", "dc_shell"],
    "place_route": ["nextpnr"],
    "formal":      ["sby", "eqy", "jaspergold", "vc_formal"],
    "lint":        ["verible-verilog-lint", "verilator", "svlint", "spyglass"],
    "waveform":    ["surfer", "gtkwave", "verdi"],
    "program":     ["openfpgaloader"],
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
