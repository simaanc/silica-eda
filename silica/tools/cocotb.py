"""MCP tool: run_cocotb."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import cocotb_runner
from silica.tools._config_dispatch import check_enabled
from silica.tools._sources import expand_sources


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def run_cocotb(
        sources: list[str],
        test_module: str,
        toplevel: str,
        simulator: str = "icarus",
        timeout: int = 120,
    ) -> dict:
        """Run a cocotb (Python) testbench against an HDL design.

        cocotb writes testbenches as Python coroutines instead of an HDL
        testbench; this builds the design and runs the cocotb tests via
        cocotb's runner, returning per-test pass/fail.

        Args:
            sources: HDL design files. May include ``.f`` filelists (one path
                     per line), expanded in place.
            test_module: Path to the Python cocotb test file (contains the
                     @cocotb.test() coroutines).
            toplevel: Top-level HDL module cocotb instantiates.
            simulator: "icarus" | "verilator" | "ghdl" | "questa" | "xcelium"
                     | "vcs". Icarus is the most common cocotb pairing.
            timeout: Seconds before killing the build+test run.

        Returns:
            {simulator, passed, failed, tests [{name, status, time, message}],
             raw_stdout, raw_stderr} or {"error": str} (cocotb/simulator
             missing, module not found, or build failed before any test ran).
        """
        disabled = check_enabled("simulation", simulator)
        if disabled:
            return {"error": disabled}

        try:
            design = expand_sources(sources)
        except OSError as exc:
            return {"error": f"Could not read filelist: {exc}"}
        if not design:
            return {"error": "No source files provided."}

        return cocotb_runner.run(
            design,
            test_module=test_module,
            toplevel=toplevel,
            simulator=simulator,
            timeout=timeout,
        )
