"""Verdi adapter — Synopsys Verdi waveform viewer (fire-and-forget)."""

import subprocess

from silica.tools._config_dispatch import resolve


def launch(trace_file: str) -> dict:
    """Open a VCD/FSDB trace file in Verdi (fire-and-forget).

    Supports .vcd, .fsdb, and other formats Verdi understands.
    """
    binary = resolve("verdi")
    if not binary:
        return {
            "launched": False,
            "error": "verdi not found. Verdi requires a Synopsys license.",
        }

    # Verdi auto-detects format from extension; -ssf for FSDB, plain arg for VCD
    if trace_file.endswith(".fsdb"):
        cmd = [binary, "-ssf", trace_file]
    else:
        cmd = [binary, trace_file]

    subprocess.Popen(cmd)
    return {
        "viewer": "verdi",
        "launched": True,
        "trace": trace_file,
    }
