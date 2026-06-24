"""Verible adapter — SystemVerilog linting via verible-verilog-lint."""

import re
import shutil
import subprocess
from typing import Any

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
    binary = shutil.which("verible-verilog-lint")
    if not binary:
        return _not_found()

    cmd = [binary]
    if ruleset == "all":
        cmd.append("--ruleset=all")
    elif ruleset != "default":
        cmd += [f"--rules={ruleset}"]
    cmd.append(file)

    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

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
        "error": "verible-verilog-lint not found. Install from https://github.com/chipsalliance/verible/releases",
    }
