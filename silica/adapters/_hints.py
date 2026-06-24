"""Cross-platform install hint strings for EDA tools."""

import platform

_HINTS: dict[str, dict[str, str]] = {
    "verilator": {
        "Darwin":  "brew install verilator",
        "Linux":   "sudo apt install verilator          # Ubuntu/Debian\n"
                   "sudo dnf install verilator          # Fedora/RHEL\n"
                   "sudo pacman -S verilator            # Arch",
        "Windows": "WSL2 recommended: wsl --install, then: sudo apt install verilator\n"
                   "Native build: https://verilator.org/guide/latest/install.html",
    },
    "iverilog": {
        "Darwin":  "brew install icarus-verilog",
        "Linux":   "sudo apt install iverilog           # Ubuntu/Debian\n"
                   "sudo dnf install iverilog           # Fedora/RHEL\n"
                   "sudo pacman -S iverilog             # Arch",
        "Windows": "WSL2 recommended: wsl --install, then: sudo apt install iverilog\n"
                   "Native build: https://github.com/steveicarus/iverilog",
    },
    "yosys": {
        "Darwin":  "brew install yosys",
        "Linux":   "sudo apt install yosys             # Ubuntu/Debian\n"
                   "sudo dnf install yosys             # Fedora/RHEL\n"
                   "sudo pacman -S yosys               # Arch",
        "Windows": "WSL2 recommended: wsl --install, then: sudo apt install yosys\n"
                   "Native build: https://github.com/YosysHQ/yosys",
    },
    "verible-verilog-lint": {
        "Darwin":  "brew install verible",
        "Linux":   "Download the release binary from:\n"
                   "https://github.com/chipsalliance/verible/releases\n"
                   "sudo apt install verible           # Ubuntu 22.04+",
        "Windows": "WSL2 recommended: wsl --install, then install Verible in WSL\n"
                   "Native binary: https://github.com/chipsalliance/verible/releases",
    },
    "surfer": {
        "Darwin":  "brew install surfer",
        "Linux":   "Download from https://gitlab.com/surfer-project/surfer/-/releases\n"
                   "(apt/dnf packages are outdated — use the GitLab release binary)",
        "Windows": "Download from https://gitlab.com/surfer-project/surfer/-/releases",
    },
    "gtkwave": {
        "Darwin":  "brew install --cask gtkwave\n"
                   "Note: GTKWave is discontinued upstream — consider Surfer instead",
        "Linux":   "sudo apt install gtkwave           # Ubuntu/Debian\n"
                   "sudo dnf install gtkwave           # Fedora/RHEL\n"
                   "sudo pacman -S gtkwave             # Arch",
        "Windows": "Download from https://gtkwave.sourceforge.net/\n"
                   "Or use Surfer: https://gitlab.com/surfer-project/surfer/-/releases",
    },
}

_FALLBACK = "See the project's official documentation for install instructions."


def install_hint(tool: str) -> str:
    """Return a platform-appropriate install hint for the given EDA tool binary."""
    system = platform.system()  # "Darwin" | "Linux" | "Windows"
    tool_hints = _HINTS.get(tool, {})
    return tool_hints.get(system, tool_hints.get("Linux", _FALLBACK))
