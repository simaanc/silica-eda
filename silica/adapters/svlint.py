"""svlint adapter — Rust-based SystemVerilog linter."""

import re
import subprocess

from silica.adapters._hints import install_hint
from silica.detect import resolve

# svlint 0.9 output format (colored even when piped; colors are stripped first):
# Fail: rule_name
#    --> filename.sv:10:5
#    ...
#   |  ^^^^ hint  : hint text
# Error: parse error
#    --> filename.sv:3:1
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[A-Za-z]|\([A-Z])")
_BLOCK_RE = re.compile(
    r"^(Fail|Error):\s*(.+?)\s*\n\s*-->\s*(.+):(\d+):(\d+)\s*$",
    re.MULTILINE,
)
_BLOCK_HINT_RE = re.compile(r"hint\s*:\s*(.+)$", re.MULTILINE)

# Older output formats:
# Fail: filename.sv: 10:5  rule_name
#       hint text
# or: filename.sv:10:5: hint [rule]
_FAIL_RE = re.compile(
    r"^Fail:\s*(\S+):\s*(\d+):(\d+)\s+(\S+)",
    re.MULTILINE,
)
_HINT_RE = re.compile(
    r"^(\S+\.s?vh?):(\d+):(\d+):\s*(.+?)(?:\s+\[(\S+)\])?$",
    re.MULTILINE,
)


def _parse(output: str) -> list[dict]:
    output = _ANSI_RE.sub("", output)
    results: list[dict] = []
    blocks = list(_BLOCK_RE.finditer(output))
    for i, m in enumerate(blocks):
        kind, rule, f, line, _col = m.groups()
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(output)
        hint = _BLOCK_HINT_RE.search(output, m.end(), end)
        results.append({
            "file": f.strip(),
            "line": int(line),
            "severity": "error" if kind == "Error" else "warning",
            "rule_id": rule.strip() if kind == "Fail" else "svlint",
            "message": hint.group(1).strip() if hint else rule.strip(),
        })
    if results:
        return results
    # Then the one-line format
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
