"""openFPGALoader adapter — FPGA bitstream programming."""

import re
import subprocess

from silica import oss_cad_suite
from silica.adapters._hints import install_hint

_ERROR_KEYWORDS = ["Error", "error:", "failed", "FAILED", "Unable to"]
# Xilinx loads end with "ir: 1 isc_done 1 isc_ena 0 init 1 done 1". When the
# device rejects the bitstream it reports done 0 but still exits 0.
_XILINX_DONE_LOW_RE = re.compile(r"^ir:.*\bdone 0\b", re.MULTILINE)


def run(
    bitstream: str,
    board: str | None = None,
    cable: str | None = None,
    device: str | None = None,
    spi_flash: bool = False,
    timeout: int = 60,
) -> dict:
    """Program an FPGA using openFPGALoader.

    Args:
        bitstream: Path to the bitstream file (.bit, .bin, etc.)
        board: Board name preset, e.g. "ice40_hx8k_b_evn", "arty", "basys3".
        cable: JTAG cable, e.g. "ft2232", "digilent_hs2", "jlink".
        device: Explicit FPGA part override, e.g. "xc7a35t". Optional.
        spi_flash: When True, write to SPI flash (persistent) instead of SRAM.
        timeout: Seconds before killing openFPGALoader.
    """
    binary = oss_cad_suite.which("openFPGALoader")
    if not binary:
        return _not_found()

    cmd = [binary]
    if board:
        cmd += ["-b", board]
    if cable:
        cmd += ["-c", cable]
    if device:
        cmd += ["-d", device]
    if spi_flash:
        cmd.append("-f")
    cmd.append(bitstream)

    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=oss_cad_suite.env_with_suite(),
        )
    except subprocess.TimeoutExpired:
        return {
            "tool": "openFPGALoader",
            "exit_code": -1,
            "success": False,
            "errors": [{"message": f"openFPGALoader timed out after {timeout}s"}],
            "raw_output": "",
        }

    raw = cp.stdout + cp.stderr
    success = cp.returncode == 0

    errors = []
    if success and _XILINX_DONE_LOW_RE.search(raw):
        success = False
        errors.append({"message": (
            "The FPGA did not assert DONE after loading, so it is not "
            "configured; the bitstream was rejected — see raw_output"
        )})
    elif not success:
        for line in raw.splitlines():
            if any(kw in line for kw in _ERROR_KEYWORDS):
                errors.append({"message": line.strip()})
        if not errors:
            errors.append({"message": "Programming failed — see raw_output"})

    return {
        "tool": "openFPGALoader",
        "exit_code": cp.returncode,
        "success": success,
        "errors": errors,
        "raw_output": raw,
    }


def _not_found() -> dict:
    return {
        "tool": "openFPGALoader",
        "exit_code": -1,
        "success": False,
        "errors": [{"message": f"openFPGALoader not found.\n{install_hint('openfpgaloader')}"}],
        "raw_output": "",
    }
