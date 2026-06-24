"""MCP tool: run_formal."""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import sby as sby_adapter


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def run_formal(
        sby_file: str | None = None,
        files: list[str] | None = None,
        top: str | None = None,
        mode: str = "prove",
        depth: int = 20,
        engine: str = "auto",
        timeout: int = 300,
    ) -> dict:
        """Run formal verification with SymbiYosys and return structured results.

        Two usage modes:
          1. Pass sby_file — run an existing .sby config file directly.
          2. Pass files + top — auto-generate a .sby config and run it.

        Args:
            sby_file: Path to an existing .sby config file.
            files: RTL source files (used when sby_file is omitted).
            top: Top module name (used when sby_file is omitted).
            mode: "prove" | "bmc" | "cover" | "live". Default: "prove".
            depth: Bound depth for bmc/prove. Default: 20.
            engine: "auto" (detect z3/bitwuzla) or explicit e.g. "smtbmc z3".
            timeout: Seconds before killing sby. Default: 300.

        Returns a FormalResult dict:
            status: "PASS" | "FAIL" | "ERROR" | "UNKNOWN"
            rc: exit code (0=PASS, 2=FAIL, 16=ERROR)
            failures: [{property, file, line}]
            traces: [path to counterexample VCD — open with silica waveform viewer]
            warnings: [{file, line, message}]
            errors: [{file, line, message}]
            workdir: sby work directory (persists so traces can be opened)
            raw_output: full sby log
        """
        if sby_file:
            return sby_adapter.run(sby_file, timeout=timeout)

        if not files or not top:
            return {
                "status": "ERROR",
                "rc": -1,
                "failures": [],
                "traces": [],
                "warnings": [],
                "errors": [{"file": "", "line": 0, "message":
                    "Provide either sby_file or both files + top."}],
                "workdir": "",
                "raw_output": "",
            }

        # Generate a .sby file, write to a temp path alongside the sources,
        # then run it so relative [files] paths resolve correctly.
        sby_content = sby_adapter.generate_sby(
            files=files,
            top=top,
            mode=mode,
            depth=depth,
            engine=engine,
        )

        tmp_dir = Path(tempfile.mkdtemp(prefix="silica_sby_gen_"))
        sby_path = tmp_dir / f"{top}.sby"
        sby_path.write_text(sby_content, encoding="utf-8")

        result = sby_adapter.run(str(sby_path), timeout=timeout)
        result["generated_sby"] = sby_content
        return result
