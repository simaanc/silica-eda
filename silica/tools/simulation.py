"""MCP tool: run_simulation."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import icarus, verilator
from silica.adapters import vcs, questa, xcelium
from silica.adapters._hints import install_hint
from silica.tools._config_dispatch import pick

# Maps registry name → adapter identifier used below
_SIM_ADAPTERS = {
    "verilator": "verilator",
    "iverilog":  "icarus",
    "vcs":       "vcs",
    "questa":    "questa",
    "xcelium":   "xcelium",
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
    ) -> dict:
        """Run RTL simulation and return structured diagnostics.

        Args:
            file: Path to the DUT source file (.sv or .v).
            testbench: Path to the testbench file.
            simulator: "auto" | "verilator" | "icarus" | "vcs" | "questa" | "xcelium".
                       Auto uses config priority order.
            top: Top module name (inferred from testbench filename if omitted).
            timeout: Seconds before killing the simulator process.
            trace: When True, capture a VCD waveform trace. Returns trace_vcd path
                   in the result dict. Pass that path to launch_waveform to open it.

        Returns a SimulationResult dict:
            exit_code, errors [{file, line, severity, message}], warnings,
            raw_stdout, raw_stderr, trace_vcd (str path or None)
        """
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
                            "No simulator found. Install Verilator or Icarus Verilog:\n"
                            f"Verilator: {install_hint('verilator')}\n"
                            f"Icarus:    {install_hint('iverilog')}"
                        ),
                    }],
                    "warnings": [],
                    "raw_stdout": "",
                    "raw_stderr": "",
                    "trace_vcd": None,
                }

        if simulator == "verilator":
            return verilator.run(file, testbench, top=top, timeout=timeout, trace=trace)
        elif simulator == "icarus":
            return icarus.run(file, testbench, top=top, timeout=timeout, trace=trace)
        elif simulator == "vcs":
            return vcs.run(file, testbench, top=top, timeout=timeout, trace=trace)
        elif simulator == "questa":
            return questa.run(file, testbench, top=top, timeout=timeout, trace=trace)
        elif simulator == "xcelium":
            return xcelium.run(file, testbench, top=top, timeout=timeout, trace=trace)
        else:
            return {
                "exit_code": -1,
                "errors": [{
                    "file": "",
                    "line": 0,
                    "severity": "error",
                    "message": (
                        f"Unknown simulator '{simulator}'. "
                        "Supported: auto, verilator, icarus, vcs, questa, xcelium."
                    ),
                }],
                "warnings": [],
                "raw_stdout": "",
                "raw_stderr": "",
                "trace_vcd": None,
            }
