"""svlint adapter — Rust-based SystemVerilog linter."""

import re
import subprocess

from silica.adapters._hints import install_hint
from silica.detect import resolve

# svlint output format:
# Fail: filename.sv: 10:5  rule_name
#       hint text
# or (newer): filename.sv:10:5: hint [rule]
_FAIL_RE = re.compile(
    r"^Fail:\s*(\S+):\s*(\d+):(\d+)\s+(\S+)",
    re.MULTILINE,
)
_HINT_RE = re.compile(
    r"^(\S+\.s?vh?):(\d+):(\d+):\s*(.+?)(?:\s+\[(\S+)\])?$",
    re.MULTILINE,
)


def _parse(output: str) -> list[dict]:
    results: list[dict] = []
    # Try newer format first
    for m in _HINT_RE.finditer(output):
        f, line, _col, message, rule_id = m.groups()
        results.append({
            "file": f.strip(),
            "line": int(line),
            "severity": "warning",
            "rule_id": rule_id.strip() if rule_id else "svlint",
            "message": message.strip(),
        })
    if results:
        return results
    # Fall back to older "Fail:" format
    for m in _FAIL_RE.finditer(output):
        f, line, _col, rule_id = m.groups()
        results.append({
            "file": f.strip(),
            "line": int(line),
            "severity": "warning",
            "rule_id": rule_id.strip(),
            "message": rule_id.strip(),
        })
    return results


def run(file: str, ruleset: str = "default", timeout: int = 30) -> dict:
    """Lint a SystemVerilog file with svlint."""
    binary = resolve("svlint")
    if not binary:
        return _not_found()

    cmd = [binary]
    # svlint supports --config for custom rulesets; default uses .svlint.toml if present
    if ruleset not in ("default", ""):
        cmd += ["--config", ruleset]
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
            "tool": "svlint",
            "raw_output": "",
            "error": f"svlint timed out after {timeout}s",
        }

    combined = cp.stdout + cp.stderr
    warnings = _parse(combined)

    return {
        "warnings": warnings,
        "tool": "svlint",
        "raw_output": combined,
    }


def _not_found() -> dict:
    return {
        "warnings": [],
        "tool": "svlint",
        "raw_output": "",
        "error": f"svlint not found.\n{install_hint('svlint')}",
    }
