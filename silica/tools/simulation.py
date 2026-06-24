"""MCP tool: run_simulation."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import icarus, verilator
from silica.adapters._hints import install_hint
from silica.tools._config_dispatch import pick

# Maps registry name → adapter identifier used below
_SIM_ADAPTERS = {"verilator": "verilator", "iverilog": "icarus"}


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def run_simulation(
        file: str,
        testbench: str,
        simulator: str = "auto",
        top: str | None = None,
        timeout: int = 60,
    ) -> dict:
        """Run RTL simulation and return structured diagnostics.

        Args:
            file: Path to the DUT source file (.sv or .v).
            testbench: Path to the testbench file.
            simulator: "auto" | "verilator" | "icarus". Auto uses config priority order.
            top: Top module name (inferred from testbench filename if omitted).
            timeout: Seconds before killing the simulator process.

        Returns a SimulationResult dict:
            exit_code, errors [{file, line, severity, message}], warnings, raw_stdout, raw_stderr
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
                }

        if simulator == "verilator":
            return verilator.run(file, testbench, top=top, timeout=timeout)
        elif simulator == "icarus":
            return icarus.run(file, testbench, top=top, timeout=timeout)
        else:
            return {
                "exit_code": -1,
                "errors": [{
                    "file": "",
                    "line": 0,
                    "severity": "error",
                    "message": f"Unknown simulator '{simulator}'. Supported: auto, verilator, icarus.",
                }],
                "warnings": [],
                "raw_stdout": "",
                "raw_stderr": "",
            }
