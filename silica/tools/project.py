"""MCP tools: file and project operations."""

import difflib
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica import config as cfg

_RTL_EXTENSIONS = {".sv", ".svh", ".v", ".vh", ".vhd", ".vhdl"}
_CONSTRAINT_EXTENSIONS = {".xdc", ".lpf", ".sdc", ".upf", ".pdc"}


def project_root() -> Path:
    """Resolve the project directory the file tools are confined to.

    When Claude Desktop (and other file-based clients) launch the server, its
    CWD is not the user's project, which makes the default confinement root
    useless. So the root is resolved in precedence order:

    1. the ``SILICA_PROJECT_ROOT`` env var,
    2. the ``project.root`` key in ``~/.silica/config.toml``,
    3. the server's current working directory (the historical default).

    A configured root that doesn't exist is ignored so a stale setting can't
    silently disable every file tool.
    """
    env = os.environ.get("SILICA_PROJECT_ROOT")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p.resolve()
    recorded = cfg.load().get("project", {}).get("root", "")
    if recorded:
        p = Path(recorded).expanduser()
        if p.is_dir():
            return p.resolve()
    return Path.cwd().resolve()


def _confine(file: str) -> tuple[Path | None, str | None]:
    """Resolve a path and require it to stay inside the project directory.

    The project root is :func:`project_root` (env/config/CWD). Absolute paths
    and ``..`` traversal that escape it are rejected so MCP callers cannot read
    or write arbitrary files. Relative paths are taken relative to the project
    root, not the server's CWD. Returns (path, None) on success or
    (None, error message) on escape.
    """
    root = project_root()
    path = (root / file).resolve()
    if path == root or path.is_relative_to(root):
        return path, None
    return None, (
        f"Path escapes the project directory: {file} "
        f"(resolved to {path}; project root is {root})"
    )


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def get_project_structure(root: str = ".") -> dict:
        """List the project's RTL and constraint files.

        Start here in an unfamiliar project to find the sources to pass to
        lint, run_simulation and synthesize, and the constraint file for
        run_place_route.

        Args:
            root: Directory to scan, inside the project (defaults to the
                  project root).

        Returns:
            root: the directory scanned (absolute)
            rtl_files: relative paths of .v/.sv/.svh/.vh/.vhd/.vhdl files
            constraint_files: relative paths of .xdc, .lpf, .sdc, .upf and
                .pdc files (iCE40 .pcf files are not listed)
            file_count: number of RTL files
            error: present only when root escapes the project directory
        """
        root_path, escape = _confine(root)
        if escape:
            return {"root": root, "rtl_files": [], "constraint_files": [],
                    "file_count": 0, "error": escape}
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
            file: Path to the file; must stay inside the project directory.
            start_line: First line to return (1-indexed, inclusive).
            end_line: Last line to return (1-indexed, inclusive).

        Returns:
            content: file text with line numbers, path, total_lines
        """
        path, escape = _confine(file)
        if path is None:
            return {"error": escape, "content": "", "path": file, "total_lines": 0}
        if not path.exists():
            return {
                "error": f"File not found: {file} (resolved to {path}) — use an absolute path",
                "content": "",
                "path": str(path),
                "total_lines": 0,
            }

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
            file: Path to the target file; must stay inside the project directory.
            content: Complete new file content.
            dry_run: If True (default), return a unified diff without writing. If False, write.

        Returns:
            diff: unified diff string (dry_run=True) or empty string after write
            lines_changed: number of changed lines
            written: True if file was actually written
        """
        path, escape = _confine(file)
        if path is None:
            return {
                "dry_run": dry_run,
                "written": False,
                "diff": "",
                "lines_changed": 0,
                "path": file,
                "error": escape,
            }

        if path.exists():
            original_lines = path.read_text(
                encoding="utf-8", errors="replace").splitlines(keepends=True)
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
        changed = sum(
            1 for line in diff_lines
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )

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
            root: Directory to search, inside the project (defaults to the
                  project root).
            scope: "all" | "sv" | "v" — filter by file extension.

        Returns:
            matches: [{file, line, context}] — capped at 50 entries
            match_count: total matches found (may exceed len(matches))
            truncated: True when matches were dropped by the 50-entry cap
        """
        root_path, escape = _confine(root)
        if escape:
            return {"query": query, "match_count": 0, "matches": [],
                    "truncated": False, "error": escape}
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

        return {
            "query": query,
            "match_count": len(matches),
            "matches": matches[:50],
            "truncated": len(matches) > 50,
        }

    @mcp.tool()
    def get_constraints(file: str) -> dict:
        """Read and return the content of a constraint file (.xdc / .sdc / .lpf / .upf).

        Args:
            file: Path to the constraint file; must stay inside the project directory.

        Returns:
            content: raw file text, path, format (inferred from extension)
        """
        path, escape = _confine(file)
        if path is None:
            return {"error": escape, "content": "", "format": "unknown"}
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
