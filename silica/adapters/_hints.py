"""Cross-platform install hint strings for EDA tools."""

import platform

_HINTS: dict[str, dict[str, str]] = {
    "verilator": {
        "Darwin":  "brew install verilator",
        "Linux":   "sudo apt install verilator          # Ubuntu/Debian\n"
                   "sudo dnf install verilator          # Fedora/RHEL\n"
                   "sudo pacman -S verilator            # Arch",
        "Windows": "OSS CAD Suite (bundles verilator, yosys, sby, gtkwave, surfer):\n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases\n"
                   "Then run environment.bat / environment.ps1 to add it to PATH.",
    },
    "iverilog": {
        "Darwin":  "brew install icarus-verilog",
        "Linux":   "sudo apt install iverilog           # Ubuntu/Debian\n"
                   "sudo dnf install iverilog           # Fedora/RHEL\n"
                   "sudo pacman -S iverilog             # Arch",
        "Windows": "OSS CAD Suite (bundles iverilog + vvp):\n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases\n"
                   "Then run environment.bat / environment.ps1 to add it to PATH.",
    },
    "yosys": {
        "Darwin":  "brew install yosys",
        "Linux":   "sudo apt install yosys             # Ubuntu/Debian\n"
                   "sudo dnf install yosys             # Fedora/RHEL\n"
                   "sudo pacman -S yosys               # Arch",
        "Windows": "OSS CAD Suite (recommended — includes yosys, sby, and solvers):\n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases",
    },
    "verible-verilog-lint": {
        "Darwin":  "brew tap chipsalliance/verible && brew install verible",
        "Linux":   "Download the static release binary from:\n"
                   "  https://github.com/chipsalliance/verible/releases\n"
                   "(no apt/dnf package available)",
        "Windows": "Download win64.zip from:\n"
                   "  https://github.com/chipsalliance/verible/releases",
    },
    "sby": {
        "Darwin":  "brew install sby\n"
                   "Also install a solver: brew install z3",
        "Linux":   "OSS CAD Suite (recommended — includes sby, yosys, and z3):\n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases\n"
                   "Or install z3 separately: pip install z3-solver",
        "Windows": "OSS CAD Suite (recommended — includes sby, yosys, and z3):\n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases",
    },
    "surfer": {
        "Darwin":  "brew install surfer",
        "Linux":   "Download from https://surfer-project.org/\n"
                   "(apt/dnf packages are outdated — use the release binary)",
        "Windows": "OSS CAD Suite (bundles surfer): \n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases\n"
                   "Or download from https://surfer-project.org/",
    },
    "gtkwave": {
        "Darwin":  "brew install --cask gtkwave\n"
                   "Note: GTKWave is discontinued upstream — consider Surfer instead",
        "Linux":   "sudo apt install gtkwave           # Ubuntu/Debian\n"
                   "sudo dnf install gtkwave           # Fedora/RHEL\n"
                   "sudo pacman -S gtkwave             # Arch",
        "Windows": "OSS CAD Suite (bundles gtkwave):\n"
                   "  https://github.com/YosysHQ/oss-cad-suite-build/releases\n"
                   "Note: GTKWave is discontinued upstream — consider Surfer instead.",
    },
    "svlint": {
        "Darwin":  "cargo install svlint\n"
                   "(requires Rust — install via: curl https://sh.rustup.rs -sSf | sh)",
        "Linux":   "cargo install svlint\n"
                   "(requires Rust — install via: curl https://sh.rustup.rs -sSf | sh)",
        "Windows": "cargo install svlint\n"
                   "(requires Rust — install via https://rustup.rs/)",
    },
}

_FALLBACK = "See the project's official documentation for install instructions."


def install_hint(tool: str) -> str:
    """Return a platform-appropriate install hint for the given EDA tool binary."""
    system = platform.system()  # "Darwin" | "Linux" | "Windows"
    tool_hints = _HINTS.get(tool, {})
    return tool_hints.get(system, tool_hints.get("Linux", _FALLBACK))
