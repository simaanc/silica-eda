"""MCP tool: format_rtl."""

import difflib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import verible
from silica.tools._config_dispatch import check_enabled, pick
from silica.tools.project import _confine

# Public tool spellings → registry name used for detection/enabled checks.
_FORMATTERS = {
    "verible": "verible-verilog-format",
    "verible-format": "verible-verilog-format",
    "verible-verilog-format": "verible-verilog-format",
}


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def format_rtl(
        file: str,
        dry_run: bool = True,
        tool: str = "auto",
        timeout: int = 30,
    ) -> dict:
        """Auto-format a SystemVerilog/Verilog file and return a unified diff.

        Call with dry_run=True first to review the diff, then dry_run=False to
        write the formatted source back. The file must stay inside the project
        directory (same confinement as write_rtl).

        Args:
            file: Path to the source file to format.
            dry_run: If True (default), return the diff without writing. If
                     False, overwrite the file with the formatted output.
            tool: "auto" | "verible". Auto uses config priority order.
            timeout: Seconds before killing the formatter.

        Returns:
            {dry_run, written, diff, lines_changed, path, tool} on success, or
            {"error": str, ...} if the file escapes the project dir, the
            formatter is missing/disabled, or formatting fails (e.g. a syntax
            error — the formatter refuses rather than mangle the source).
        """
        path, escape = _confine(file)
        if path is None:
            return {"dry_run": dry_run, "written": False, "diff": "",
                    "lines_changed": 0, "path": file, "error": escape}
        if not path.is_file():
            return {"dry_run": dry_run, "written": False, "diff": "",
                    "lines_changed": 0, "path": str(path),
                    "error": f"File not found: {file} (resolved to {path})"}

        if tool == "auto":
            chosen = pick("format")
            if not chosen:
                return {"dry_run": dry_run, "written": False, "diff": "",
                        "lines_changed": 0, "path": str(path),
                        "error": (
                            "No formatter found. Install Verible "
                            "(verible-verilog-format): "
                            "https://github.com/chipsalliance/verible/releases"
                        )}
            registry_name = chosen
        else:
            registry_name = _FORMATTERS.get(tool)
            if registry_name is None:
                return {"dry_run": dry_run, "written": False, "diff": "",
                        "lines_changed": 0, "path": str(path),
                        "error": (
                            f"Unknown formatter '{tool}'. Supported: auto, verible."
                        )}
            disabled = check_enabled("format", registry_name)
            if disabled:
                return {"dry_run": dry_run, "written": False, "diff": "",
                        "lines_changed": 0, "path": str(path), "error": disabled}

        result = verible.format_src(str(path), timeout=timeout)
        if "error" in result:
            return {"dry_run": dry_run, "written": False, "diff": "",
                    "lines_changed": 0, "path": str(path), "error": result["error"]}

        original = path.read_text(encoding="utf-8", errors="replace")
        formatted = result["formatted"]

        diff_lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            formatted.splitlines(keepends=True),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
        ))
        diff_str = "".join(diff_lines)
        changed = sum(
            1 for line in diff_lines
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )

        if dry_run or not diff_str:
            return {"dry_run": dry_run, "written": False, "diff": diff_str,
                    "lines_changed": changed, "path": str(path),
                    "tool": "verible-verilog-format"}

        path.write_text(formatted, encoding="utf-8")
        return {"dry_run": False, "written": True, "diff": diff_str,
                "lines_changed": changed, "path": str(path),
                "tool": "verible-verilog-format"}
