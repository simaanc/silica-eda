"""MCP tools: file and project operations."""

import difflib
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_RTL_EXTENSIONS = {".sv", ".svh", ".v", ".vh", ".vhd", ".vhdl"}
_CONSTRAINT_EXTENSIONS = {".xdc", ".lpf", ".sdc", ".upf", ".pdc"}


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def get_project_structure(root: str = ".") -> dict:
        """Return the RTL file tree and detect the likely top-level module.

        Args:
            root: Directory to scan (defaults to current working directory).

        Returns:
            files: list of relative paths to RTL/constraint files
            top_candidates: module names that are instantiated but not instances
        """
        root_path = Path(root).resolve()
        rtl_files = []
        constraint_files = []

        for p in sorted(root_path.rglob("*")):
            if p.is_file():
                if p.suffix in _RTL_EXTENSIONS:
                    rtl_files.append(str(p.relative_to(root_path)))
                elif p.suffix in _CONSTRAINT_EXTENSIONS:
                    constraint_files.append(str(p.relative_to(root_path)))

        return {
            "root": str(root_path),
            "rtl_files": rtl_files,
            "constraint_files": constraint_files,
            "file_count": len(rtl_files),
        }

    @mcp.tool()
    def read_rtl(file: str, start_line: int | None = None, end_line: int | None = None) -> dict:
        """Read an RTL file, optionally restricted to a line range.

        Args:
            file: Absolute or relative path to the file.
            start_line: First line to return (1-indexed, inclusive).
            end_line: Last line to return (1-indexed, inclusive).

        Returns:
            content: file text with line numbers, path, total_lines
        """
        path = Path(file).resolve()
        if not path.exists():
            return {"error": f"File not found: {file}", "content": "", "path": str(path), "total_lines": 0}

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        s = (start_line or 1) - 1
        e = end_line or total
        slice_ = lines[s:e]

        numbered = "\n".join(f"{s + i + 1:4d}  {line}" for i, line in enumerate(slice_))

        return {
            "path": str(path),
            "total_lines": total,
            "start_line": s + 1,
            "end_line": s + len(slice_),
            "content": numbered,
        }

    @mcp.tool()
    def write_rtl(file: str, content: str, dry_run: bool = True) -> dict:
        """Write (or diff) proposed RTL content to a file.

        Always call with dry_run=True first to review the unified diff before committing.

        Args:
            file: Absolute or relative path to the target file.
            content: Complete new file content.
            dry_run: If True (default), return a unified diff without writing. If False, write.

        Returns:
            diff: unified diff string (dry_run=True) or empty string after write
            lines_changed: number of changed lines
            written: True if file was actually written
        """
        path = Path(file).resolve()

        if path.exists():
            original_lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        else:
            original_lines = []

        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        diff_lines = list(difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
        ))
        diff_str = "".join(diff_lines)
        changed = sum(1 for l in diff_lines if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))

        if dry_run:
            return {
                "dry_run": True,
                "written": False,
                "diff": diff_str,
                "lines_changed": changed,
                "path": str(path),
            }

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")

        return {
            "dry_run": False,
            "written": True,
            "diff": diff_str,
            "lines_changed": changed,
            "path": str(path),
        }

    @mcp.tool()
    def search_rtl(query: str, root: str = ".", scope: str = "all") -> dict:
        """Grep across project RTL files with surrounding context.

        Args:
            query: Search string (literal, not regex).
            root: Directory to search.
            scope: "all" | "sv" | "v" — filter by file extension.

        Returns:
            matches: [{file, line, context}]
        """
        root_path = Path(root).resolve()
        ext_filter = {
            "sv": {".sv", ".svh"},
            "v": {".v", ".vh"},
            "all": _RTL_EXTENSIONS,
        }.get(scope, _RTL_EXTENSIONS)

        matches = []
        query_lower = query.lower()

        for p in sorted(root_path.rglob("*")):
            if not p.is_file() or p.suffix not in ext_filter:
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    ctx_start = max(0, i - 2)
                    ctx_end = min(len(lines), i + 3)
                    context = "\n".join(
                        f"{ctx_start + j + 1:4d}  {lines[ctx_start + j]}"
                        for j in range(ctx_end - ctx_start)
                    )
                    matches.append({
                        "file": str(p.relative_to(root_path)),
                        "line": i + 1,
                        "context": context,
                    })

        return {"query": query, "match_count": len(matches), "matches": matches[:50]}

    @mcp.tool()
    def get_constraints(file: str) -> dict:
        """Read and return the content of a constraint file (.xdc / .sdc / .lpf / .upf).

        Args:
            file: Path to the constraint file.

        Returns:
            content: raw file text, path, format (inferred from extension)
        """
        path = Path(file).resolve()
        if not path.exists():
            return {"error": f"File not found: {file}", "content": "", "format": "unknown"}

        fmt = {
            ".xdc": "xdc",
            ".sdc": "sdc",
            ".lpf": "lpf",
            ".upf": "upf",
            ".pdc": "pdc",
        }.get(path.suffix, "unknown")

        return {
            "path": str(path),
            "format": fmt,
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }
