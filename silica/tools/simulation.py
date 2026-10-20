"""MCP tool: run_simulation."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

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


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def run_simulation(
        file: str,
        testbench: str,
        simulator: str = "auto",
        top: str | None = None,
        timeout: int = 60,
        trace: bool = False,
        extra_sources: list[str] | None = None,
        coverage: bool = False,
    ) -> dict:
        """Run RTL simulation and return structured diagnostics.

        The simulator runs in the DUT file's directory, so relative paths in
        the testbench (e.g. $readmemh("../fw/firmware.hex")) resolve from
        there, with or without trace/coverage. A failing $fatal/$error comes
        back in errors with its file, line and message.

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
            trace: When True, collect the VCD the testbench writes (it must call
                   $dumpfile/$dumpvars) into a persistent directory and return
                   its path as trace_vcd. Read it with read_waveform, or open it
                   with launch_waveform.
            extra_sources: Additional design files (submodules, packages)
                   compiled alongside the DUT. Each entry may itself be a ``.f``
                   filelist, which is expanded in place.
            coverage: When True, collect line/toggle coverage (Verilator only).
                   Returns coverage_dat in the result — pass it to
                   read_coverage for a structured report.

        Returns a SimulationResult dict:
            exit_code, errors [{file, line, severity, message}], warnings,
            raw_stdout, raw_stderr, trace_vcd (str path or None), and
            coverage_dat (str path or None, Verilator + coverage=True only)
        """
        if coverage and simulator not in ("auto", "verilator"):
            return _error_result(
                file,
                f"coverage=True is only supported with Verilator, not "
                f"'{simulator}'. Re-run with simulator='verilator'.",
            )
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

        # Coverage is Verilator-only; catch the case where auto resolved to
        # another simulator so the caller gets a clear message, not a silent
        # missing coverage_dat.
        if coverage and simulator != "verilator":
            return _error_result(
                file,
                f"coverage=True is only supported with Verilator, but the "
                f"selected simulator is '{simulator}'. Re-run with "
                f"simulator='verilator'.",
            )

        if simulator == "verilator":
            return verilator.run(dut, testbench, top=top, timeout=timeout,
                                 trace=trace, extra_sources=extra,
                                 coverage=coverage)
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
