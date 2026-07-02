"""MCP tool: lint."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import verible, verilator
from silica.adapters import svlint, spyglass
from silica.tools._config_dispatch import check_enabled, pick

_LINT_TOOL_MAP = {
    "verible-verilog-lint": "verible",
    "verilator":            "verilator",
    "svlint":               "svlint",
    "spyglass":             "spyglass",
}


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def lint(
        file: str,
        ruleset: str = "default",
        tool: str = "auto",
        timeout: int = 30,
    ) -> dict:
        """Lint a SystemVerilog/Verilog file and return structured warnings.

        Args:
            file: Path to the source file to lint.
            ruleset: "default" | "all" | comma-separated rule list (tool-specific).
            tool: "auto" | "verible" | "verilator" | "svlint" | "spyglass".
                  Auto uses config priority order.
            timeout: Seconds before killing the linter.

        Returns a LintResult dict:
            warnings [{file, line, severity, rule_id, message}], tool, raw_output
        """
        if tool == "auto":
            chosen = pick("lint")
            tool = _LINT_TOOL_MAP.get(chosen, "") if chosen else ""
            if not tool:
                return {
                    "warnings": [],
                    "tool": "none",
                    "raw_output": "",
                    "error": (
                        "No linter found. Install Verible: "
                        "https://github.com/chipsalliance/verible/releases"
                    ),
                }
        else:
            # Explicit override — respect the user's configured enabled list.
            disabled = check_enabled("lint", tool)
            if disabled:
                return {
                    "warnings": [],
                    "tool": tool,
                    "raw_output": "",
                    "error": disabled,
                }

        if tool == "verible":
            return verible.run(file, ruleset=ruleset, timeout=timeout)

        if tool == "verilator":
            result = verilator.lint_only(file, timeout=timeout)
            warnings = [
                {**w, "rule_id": "verilator"}
                for w in result.get("warnings", [])
            ]
            return {
                "warnings": warnings,
                "tool": "verilator",
                "raw_output": result.get("raw_stderr", ""),
            }

        if tool == "svlint":
            return svlint.run(file, ruleset=ruleset, timeout=timeout)

        if tool == "spyglass":
            return spyglass.run(file, ruleset=ruleset, timeout=timeout)

        return {
            "warnings": [],
            "tool": tool,
            "raw_output": "",
            "error": (
                f"Unknown lint tool '{tool}'. "
                "Supported: auto, verible, verilator, svlint, spyglass."
            ),
        }
