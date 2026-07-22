"""Verible adapter — SystemVerilog linting via verible-verilog-lint."""

import re
import subprocess
from typing import Any

from silica.adapters._hints import install_hint
from silica.detect import resolve

# filename.sv:10:5: message [rule-id]
# filename.sv:10:5: message  (no rule-id)
_WARN_RE = re.compile(
    r"^([^:]+):(\d+):(\d+):\s*(.+?)(?:\s+\[([^\]]+)\])?$",
    re.MULTILINE,
)


def _parse(output: str, file: str) -> list[dict]:
    warnings: list[dict] = []
    for m in _WARN_RE.finditer(output):
        f, line, _col, message, rule_id = m.groups()
        entry: dict[str, Any] = {
            "file": f.strip(),
            "line": int(line),
            "severity": "warning",
            "rule_id": rule_id.strip() if rule_id else "unknown",
            "message": message.strip(),
        }
        warnings.append(entry)
    return warnings


def run(file: str, ruleset: str = "default", timeout: int = 30) -> dict:
    """Lint a SystemVerilog file with verible-verilog-lint."""
    binary = resolve("verible-verilog-lint")
    if not binary:
        return _not_found()

    cmd = [binary]
    if ruleset == "all":
        cmd.append("--ruleset=all")
    elif ruleset != "default":
        cmd += [f"--rules={ruleset}"]
    cmd.append(file)

    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # A hung tool must not crash the MCP server — report it structurally.
        return {
            "warnings": [],
            "tool": "verible-verilog-lint",
            "raw_output": "",
            "error": f"verible-verilog-lint timed out after {timeout}s",
        }

    combined = cp.stdout + cp.stderr
    warnings = _parse(combined, file)

    return {
        "warnings": warnings,
        "tool": "verible-verilog-lint",
        "raw_output": combined,
    }


def _not_found() -> dict:
    return {
        "warnings": [],
        "tool": "verible-verilog-lint",
        "raw_output": "",
        "error": f"verible-verilog-lint not found.\n{install_hint('verible-verilog-lint')}",
    }


def format_src(file: str, timeout: int = 30) -> dict:
    """Format a SystemVerilog file with verible-verilog-format.

    Emits the formatted source to stdout (not --inplace) so the tool layer can
    diff and path-confine before writing. Returns {"formatted": str} on success
    or {"error": str} — including on a syntax error, which the formatter
    refuses (exit != 0) rather than mangling.
    """
    binary = resolve("verible-verilog-format")
    if not binary:
        return {
            "error": (
                "verible-verilog-format not found.\n"
                f"{install_hint('verible-verilog-format')}"
            ),
        }
    try:
        cp = subprocess.run(
            [binary, file],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"verible-verilog-format timed out after {timeout}s"}

    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout).strip()
        return {"error": f"verible-verilog-format could not format {file}: {detail}"}

    return {"formatted": cp.stdout, "raw_output": cp.stderr}
