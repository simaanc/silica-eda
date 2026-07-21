"""Tool binary detection shared by the tools and adapters layers.

Lives below both layers so adapters never import upward into silica.tools.
"""

import shutil

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
    "ghdl": "ghdl",
    "yosys": "yosys",
    "vivado": "vivado",
    "quartus": "quartus_sh",
    "dc_shell": ["dc_shell", "dc_shell-t"],
    "nextpnr": ["nextpnr-ice40", "nextpnr-ecp5", "nextpnr-nexus",
                "nextpnr-machxo2", "nextpnr-generic"],
    "sby": "sby",
    "jaspergold": ["jg", "jaspergold"],
    "vc_formal": ["vcf", "vc_static_shell"],
    "eqy": "eqy",
    "verible-verilog-lint": "verible-verilog-lint",
    "verible-verilog-format": "verible-verilog-format",
    "svlint": "svlint",
    "spyglass": ["spyglass", "sg_shell", "vc_static_shell"],
    "surfer": "surfer",
    "gtkwave": "gtkwave",
    "verdi": "verdi",
    "openfpgaloader": "openFPGALoader",
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
