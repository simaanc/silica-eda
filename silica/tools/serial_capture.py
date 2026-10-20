"""MCP tool: capture_serial."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import serial_capture


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def capture_serial(
        port: str,
        baud: int = 115200,
        duration: float = 5.0,
        send: str | None = None,
        send_delay: float = 0.0,
        expect: str | None = None,
        stop_on_match: bool = True,
    ) -> dict:
        """Capture a board's UART output, optionally sending text first.

        Use after program_device to check what the design prints, e.g. a
        firmware banner, or that typed characters are echoed. Only the port
        you name is opened; silica never scans for serial ports.

        Args:
            port: Serial device to open, e.g. "/dev/ttyUSB1" or
                  "/dev/serial/by-id/usb-...-if01-port0" (Linux), "COM4" (Windows).
                  On boards with an FTDI JTAG+UART bridge the UART is usually
                  the second interface (if01).
            baud: Baud rate; 8N1, no flow control.
            duration: Seconds to listen (at most 600).
            send: Text to write once send_delay has passed, e.g. "hello\\r".
            send_delay: Seconds to listen before sending.
            expect: Regex searched for in the captured text, e.g. "Silica .* SoC".
            stop_on_match: Stop as soon as expect matches (default) instead of
                  listening for the full duration.

        Returns a SerialCapture dict:
            port, baud, elapsed_s, bytes_received, bytes_sent,
            lines [{t, text, partial?}] (t = seconds from the start of the
            capture to the line's first byte), text (everything received,
            UTF-8 with replacement characters), expect, matched (bool, or
            None without expect), match (the matched text).
            On failure also error (message) and, when there is one, fix
            (a command or step to resolve it, e.g. granting port access).
        """
        return serial_capture.run(
            port,
            baud=baud,
            duration=duration,
            send=send,
            send_delay=send_delay,
            expect=expect,
            stop_on_match=stop_on_match,
        )
