"""MCP tool: synthesize."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import dc_shell, quartus, vivado, yosys
from silica.tools._config_dispatch import check_enabled, pick
from silica.tools._sources import expand_sources


def _synth_error(tool: str, target: str, message: str) -> dict:
    """A SynthesisResult-shaped dict carrying a single tool-level error."""
    return {
        "tool": tool,
        "target": target,
        "exit_code": -1,
        "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                        "lut_pct": 0.0, "ff_pct": 0.0},
        "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
        "netlist": None,
        "warnings": [],
        "errors": [{"file": "", "line": 0, "severity": "error",
                    "message": message}],
        "raw_output": "",
    }


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def synthesize(
        top_module: str,
        files: list[str],
        target: str = "generic",
        tool: str = "auto",
        timeout: int = 120,
    ) -> dict:
        """Synthesize RTL and return structured utilization and timing summary.

        Args:
            top_module: Name of the top-level module to synthesize.
            files: List of source file paths (.sv / .v).
            target: Synthesis target.
                    Yosys:   "generic" | "ice40" | "ecp5" | "xilinx" | "gowin"
                    Vivado:  FPGA part string e.g. "xc7a35tcsg324-1", or shorthand
                             "artix7" | "kintex7" | "ultrascale" | "ultrascale+" | "zynq"
                    Quartus: device family e.g. "cyclone5" | "arria10" | "stratix10"
                    DC Shell: technology library path, or "generic"
            tool: "auto" | "yosys" | "vivado" | "quartus" | "dc_shell".
                  Auto uses config priority order.
            timeout: Seconds before killing the synthesis process.

        Returns a SynthesisResult dict:
            tool, target, exit_code, utilization {luts, ffs, bram, dsp, lut_pct, ff_pct},
            timing_summary {wns, tns, failing_endpoints}, netlist, warnings, errors,
            raw_output

            netlist: path to a JSON netlist ready for run_place_route. Written by
            yosys for FPGA targets ("ice40" | "ecp5" | "xilinx" | "gowin");
            None for generic/commercial-tool runs and on failure.

            files may include ``.f`` filelists (one source path per line),
            expanded in place.
        """
        # Expand any .f filelists so a single filelist can stand in for many
        # source files.
        try:
            files = expand_sources(files)
        except OSError as exc:
            return _synth_error(tool, target, f"Could not read filelist: {exc}")
        # Every synthesis adapter runs its tool in a temp directory, where a
        # relative path no longer points at the caller's file.
        files = [str(Path(f).resolve()) for f in files]

        if tool == "auto":
            chosen = pick("synthesis")
            if not chosen:
                return {
                    "tool": "none",
                    "target": target,
                    "exit_code": -1,
                    "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                                    "lut_pct": 0.0, "ff_pct": 0.0},
                    "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
                    "netlist": None,
                    "warnings": [],
                    "errors": [{
                        "file": "", "line": 0, "severity": "error",
                        "message": (
                            "No synthesis tool found. Install Yosys "
                            "(https://github.com/YosysHQ/yosys) or add a commercial "
                            "tool (Vivado, Quartus, DC Shell) to PATH."
                        ),
                    }],
                    "raw_output": "",
                }
            tool = chosen
        else:
            # Explicit override — respect the user's configured enabled list.
            disabled = check_enabled("synthesis", tool)
            if disabled:
                return {
                    "tool": tool,
                    "target": target,
                    "exit_code": -1,
                    "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                                    "lut_pct": 0.0, "ff_pct": 0.0},
                    "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
                    "netlist": None,
                    "warnings": [],
                    "errors": [{"file": "", "line": 0, "severity": "error",
                                "message": disabled}],
                    "raw_output": "",
                }

        if tool == "yosys":
            return yosys.run(top_module, files, target=target, timeout=timeout)
        elif tool == "vivado":
            return vivado.run(top_module, files, target=target, timeout=timeout)
        elif tool == "quartus":
            return quartus.run(top_module, files, target=target, timeout=timeout)
        elif tool == "dc_shell":
            return dc_shell.run(top_module, files, target=target, timeout=timeout)
        else:
            return {
                "tool": "none",
                "target": target,
                "exit_code": -1,
                "utilization": {"luts": 0, "ffs": 0, "bram": 0, "dsp": 0,
                                "lut_pct": 0.0, "ff_pct": 0.0},
                "timing_summary": {"wns": 0.0, "tns": 0.0, "failing_endpoints": 0},
                "netlist": None,
                "warnings": [],
                "errors": [{
                    "file": "", "line": 0, "severity": "error",
                    "message": (
                        f"Unknown synthesis tool '{tool}'. "
                        "Supported: auto, yosys, vivado, quartus, dc_shell."
                    ),
                }],
                "raw_output": "",
            }
