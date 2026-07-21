"""Config-aware tool selection for auto dispatch."""

import json

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
    "format":      ["verible-verilog-format"],
    "waveform":    ["surfer", "gtkwave", "verdi"],
    "program":     ["openfpgaloader"],
}

# Alternate spellings accepted by tool entry points for the same underlying
# tool. Config enabled/priority lists use registry names; explicit overrides
# may use an adapter-side alias. Either spelling satisfies the enabled check.
_ALIASES: dict[str, set[str]] = {
    "icarus": {"icarus", "iverilog"},
    "iverilog": {"icarus", "iverilog"},
    "verible": {"verible", "verible-verilog-lint"},
    "verible-verilog-lint": {"verible", "verible-verilog-lint"},
    "verible-format": {"verible-format", "verible-verilog-format"},
    "verible-verilog-format": {"verible-format", "verible-verilog-format"},
    "openfpgaloader": {"openfpgaloader", "openFPGALoader"},
    "openFPGALoader": {"openfpgaloader", "openFPGALoader"},
}


def _category_cfg(category: str) -> dict:
    """Single accessor for a category's config block (shared by all readers)."""
    return cfg.load().get("tools", {}).get(category, {})


def pick(category: str) -> str | None:
    """Return the first available and enabled tool name for the given category.

    Respects config priority order when ~/.silica/config.toml exists;
    falls back to hardcoded defaults otherwise. Tools excluded by the
    category's enabled list are never picked. Returns None if nothing
    on PATH matches.
    """
    tools_cfg = _category_cfg(category)
    priority = tools_cfg.get("priority") or tools_cfg.get("enabled") or []

    if not priority:
        priority = _FALLBACK.get(category, [])

    for name in priority:
        if is_enabled(category, name) and resolve(name):
            return name

    return None


def is_enabled(category: str, name: str) -> bool:
    """Return True unless the category's enabled list exists and excludes the tool.

    An empty or missing enabled list means no restriction. Registry names and
    adapter aliases (icarus/iverilog, verible/verible-verilog-lint, ...) are
    interchangeable.
    """
    enabled = _category_cfg(category).get("enabled", [])
    if not enabled:
        return True  # no config — allow anything
    return any(n in enabled for n in _ALIASES.get(name, {name}))


def check_enabled(category: str, name: str) -> str | None:
    """Gate an explicit tool override against the category's enabled list.

    Returns None when the tool may be used, or an error message naming the
    rejected tool, the category, and what is currently enabled — enough for
    a calling model to retry with an allowed tool.
    """
    if is_enabled(category, name):
        return None
    enabled = _category_cfg(category).get("enabled", [])
    return (
        f'"{name}" is disabled by config for category "{category}"; '
        f"enabled: {json.dumps(enabled)}"
    )
