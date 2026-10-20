"""MCP tool: program_device."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import openfpgaloader
from silica.tools._config_dispatch import check_enabled, pick


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def program_device(
        bitstream: str,
        board: str | None = None,
        cable: str | None = None,
        device: str | None = None,
        spi_flash: bool = False,
        tool: str = "auto",
        timeout: int = 60,
    ) -> dict:
        """Program a bitstream to an FPGA device with openFPGALoader.

        Loads volatile SRAM by default, which is safe to repeat. For Xilinx
        devices success means the FPGA asserted DONE; a rejected bitstream is
        reported as a failure even though openFPGALoader exits 0. The design
        starts running as soon as loading finishes, so boot output is usually
        missed by a serial capture started afterwards (see capture_serial).

        Args:
            bitstream: Path to a loadable bitstream: .bit (Xilinx, e.g. from
                       run_place_route with arch="xilinx"; ECP5 after ecppack)
                       or .bin (iCE40 after icepack). nextpnr's .asc/.textcfg
                       text configs can't be loaded directly.
            board: Board preset name, e.g. "arty_a7_100t", "arty_a7_35t",
                   "basys3", "cmod_a7", "nexys4ddr", "ice40_hx8k_b_evn".
                   Plain "arty" is the 35T. Run openFPGALoader --list-boards
                   for all.
            cable: JTAG cable, e.g. "ft2232", "digilent_hs2", "jlink", "olimex".
                   Run openFPGALoader --list-cables for all options.
            device: Explicit FPGA part number override, e.g. "xc7a35t". Optional.
            spi_flash: When True, program SPI flash (persistent across power
                       cycles), replacing whatever design the board boots.
                       Only do this when the user asks. Default False: SRAM
                       (volatile, erased on power cycle).
            tool: "auto" | "openfpgaloader". Auto uses config priority order.
            timeout: Seconds before killing the programmer.

        Returns a ProgramResult dict:
            tool, exit_code, success, errors [{message}], raw_output
        """
        if tool == "auto":
            chosen = pick("program")
            tool = chosen or "openfpgaloader"
        else:
            # Explicit override — respect the user's configured enabled list.
            disabled = check_enabled("program", tool)
            if disabled:
                return {
                    "tool": tool,
                    "exit_code": -1,
                    "success": False,
                    "errors": [{"message": disabled}],
                    "raw_output": "",
                }

        if tool in ("openfpgaloader", "openFPGALoader"):
            return openfpgaloader.run(
                bitstream=bitstream,
                board=board,
                cable=cable,
                device=device,
                spi_flash=spi_flash,
                timeout=timeout,
            )

        return {
            "tool": "none",
            "exit_code": -1,
            "success": False,
            "errors": [{"message": f"Unknown programmer '{tool}'. "
                                   "Supported: auto, openfpgaloader."}],
            "raw_output": "",
        }
