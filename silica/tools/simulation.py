"""MCP tool: run_simulation."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import ghdl, icarus, questa, vcs, verilator, xcelium
from silica.adapters._hints import install_hint
from silica.tools._config_dispatch import check_enabled, pick
from silica.tools._sources import expand_sources

# Maps registry name → adapter identifier used below
_SIM_ADAPTERS = {
    "verilator": "verilator",
    "iverilog":  "icarus",
    "ghdl":      "ghdl",
    "vcs":       "vcs",
    "questa":    "questa",
    "xcelium":   "xcelium",
}


def _error_result(file: str, message: str) -> dict:
    """A SimulationResult-shaped dict carrying a single tool-level error."""
    return {
        "exit_code": -1,
        "errors": [{"file": file, "line": 0, "severity": "error",
                    "message": message}],
        "warnings": [],
        "raw_stdout": "",
        "raw_stderr": "",
        "trace_vcd": None,
    }


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def run_simulation(
        file: str,
        testbench: str,
        simulator: str = "auto",
        top: str | None = None,
        timeout: int = 60,
        trace: bool = False,
        extra_sources: list[str] | None = None,
    ) -> dict:
        """Run RTL simulation and return structured diagnostics.

        Args:
            file: Path to the DUT source file (.sv / .v for Verilog, .vhd for
                  VHDL). May instead be a ``.f`` filelist (one source path per
                  line); its entries become the design sources.
            testbench: Path to the testbench file.
            simulator: "auto" | "verilator" | "icarus" | "iverilog" | "ghdl" |
                       "vcs" | "questa" | "xcelium". "iverilog" is accepted as
                       an alias for "icarus". Auto uses config priority order.
            top: Top module/entity name (inferred from testbench filename if omitted).
            timeout: Seconds before killing the simulator process.
            trace: When True, capture a VCD waveform trace. Returns trace_vcd path
                   in the result dict. Pass that path to launch_waveform to open it.
            extra_sources: Additional design files (submodules, packages)
                   compiled alongside the DUT. Each entry may itself be a ``.f``
                   filelist, which is expanded in place.

        Returns a SimulationResult dict:
            exit_code, errors [{file, line, severity, message}], warnings,
            raw_stdout, raw_stderr, trace_vcd (str path or None)
        """
        # Expand any .f filelists and split into a DUT + additional sources.
        try:
            design = expand_sources([file, *(extra_sources or [])])
        except OSError as exc:
            return _error_result(file, f"Could not read filelist: {exc}")
        if not design:
            return _error_result(file, "No source files provided.")
        dut, extra = design[0], design[1:]
        if simulator == "auto":
            chosen = pick("simulation")
            if chosen in _SIM_ADAPTERS:
                simulator = _SIM_ADAPTERS[chosen]
            else:
                return {
                    "exit_code": -1,
                    "errors": [{
                        "file": file,
                        "line": 0,
                        "severity": "error",
                        "message": (
                            "No simulator found. Install Verilator, Icarus Verilog, or GHDL:\n"
                            f"Verilator: {install_hint('verilator')}\n"
                            f"Icarus:    {install_hint('iverilog')}\n"
                            f"GHDL:      {install_hint('ghdl')}"
                        ),
                    }],
                    "warnings": [],
                    "raw_stdout": "",
                    "raw_stderr": "",
                    "trace_vcd": None,
                }
        else:
            # Explicit override — respect the user's configured enabled list.
            disabled = check_enabled("simulation", simulator)
            if disabled:
                return {
                    "exit_code": -1,
                    "errors": [{"file": "", "line": 0, "severity": "error",
                                "message": disabled}],
                    "warnings": [],
                    "raw_stdout": "",
                    "raw_stderr": "",
                    "trace_vcd": None,
                }

        if simulator == "verilator":
            return verilator.run(dut, testbench, top=top, timeout=timeout,
                                 trace=trace, extra_sources=extra)
        elif simulator in ("icarus", "iverilog"):
            return icarus.run(dut, testbench, top=top, timeout=timeout,
                              trace=trace, extra_sources=extra)
        elif simulator == "ghdl":
            return ghdl.run(dut, testbench, top=top, timeout=timeout,
                            trace=trace, extra_sources=extra)
        elif simulator == "vcs":
            return vcs.run(dut, testbench, top=top, timeout=timeout,
                           trace=trace, extra_sources=extra)
        elif simulator == "questa":
            return questa.run(dut, testbench, top=top, timeout=timeout,
                              trace=trace, extra_sources=extra)
        elif simulator == "xcelium":
            return xcelium.run(dut, testbench, top=top, timeout=timeout,
                               trace=trace, extra_sources=extra)
        else:
            return {
                "exit_code": -1,
                "errors": [{
                    "file": "",
                    "line": 0,
                    "severity": "error",
                    "message": (
                        f"Unknown simulator '{simulator}'. "
                        "Supported: auto, verilator, icarus, ghdl, vcs, questa, xcelium."
                    ),
                }],
                "warnings": [],
                "raw_stdout": "",
                "raw_stderr": "",
                "trace_vcd": None,
            }
