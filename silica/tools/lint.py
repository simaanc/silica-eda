"""MCP tool: lint."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import spyglass, svlint, verible, verilator
from silica.tools._config_dispatch import check_enabled, pick
from silica.tools._sources import expand_sources

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
        extra_files: list[str] | None = None,
    ) -> dict:
        """Lint a SystemVerilog/Verilog file and return structured warnings.

        Args:
            file: Path to the source file to lint. May instead be a ``.f``
                  filelist (one path per line); each listed file is linted.
            ruleset: "default" | "all" | comma-separated rule list (tool-specific).
            tool: "auto" | "verible" | "verilator" | "svlint" | "spyglass".
                  Auto uses config priority order.
            timeout: Seconds before killing the linter (applied per file).
            extra_files: Additional files to lint. Each may itself be a ``.f``
                  filelist, expanded in place. Warnings across all files are
                  merged into one result.

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

        if tool not in ("verible", "verilator", "svlint", "spyglass"):
            return {
                "warnings": [],
                "tool": tool,
                "raw_output": "",
                "error": (
                    f"Unknown lint tool '{tool}'. "
                    "Supported: auto, verible, verilator, svlint, spyglass."
                ),
            }

        try:
            files = expand_sources([file, *(extra_files or [])])
        except OSError as exc:
            return {"warnings": [], "tool": tool, "raw_output": "",
                    "error": f"Could not read filelist: {exc}"}
        if not files:
            return {"warnings": [], "tool": tool, "raw_output": "",
                    "error": "No source files provided."}

        # Lint each file and merge. An adapter-level error (tool missing,
        # timeout) short-circuits — it applies to every file equally.
        all_warnings: list[dict] = []
        raw_chunks: list[str] = []
        for f in files:
            result = _lint_one(tool, f, ruleset, timeout)
            if "error" in result:
                return result
            all_warnings.extend(result["warnings"])
            raw_chunks.append(result["raw_output"])
        return {
            "warnings": all_warnings,
            "tool": result["tool"],
            "raw_output": "\n".join(raw_chunks),
        }


def _lint_one(tool: str, file: str, ruleset: str, timeout: int) -> dict:
    """Lint a single file with the resolved tool; returns a LintResult dict."""
    if tool == "verible":
        return verible.run(file, ruleset=ruleset, timeout=timeout)

    if tool == "verilator":
        result = verilator.lint_only(file, timeout=timeout)
        if "error" in result:
            return {"warnings": [], "tool": "verilator", "raw_output": "",
                    "error": result["error"]}
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

    # spyglass
    return spyglass.run(file, ruleset=ruleset, timeout=timeout)
