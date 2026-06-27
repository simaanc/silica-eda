"""MCP tool: run_formal."""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import sby as sby_adapter
from silica.adapters import jaspergold, vc_formal
from silica.tools._config_dispatch import pick

_FORMAL_ADAPTERS = {
    "sby":        "sby",
    "jaspergold": "jaspergold",
    "vc_formal":  "vc_formal",
}


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def run_formal(
        sby_file: str | None = None,
        files: list[str] | None = None,
        top: str | None = None,
        mode: str = "prove",
        depth: int = 20,
        engine: str = "auto",
        tool: str = "auto",
        timeout: int = 300,
    ) -> dict:
        """Run formal verification and return structured results.

        Two usage modes:
          1. Pass sby_file — run an existing .sby (SymbiYosys) or .tcl (JasperGold/VC Formal)
             config file directly.
          2. Pass files + top — auto-generate a config and run it.

        Args:
            sby_file: Path to an existing config file (.sby for SymbiYosys, .tcl for others).
            files: RTL source files (used when sby_file is omitted).
            top: Top module name (used when sby_file is omitted).
            mode: "prove" | "bmc" | "cover" | "live". Default: "prove".
            depth: Bound depth for bmc/prove. Default: 20.
            engine: "auto" (detect z3/bitwuzla) or explicit e.g. "smtbmc z3".
                    Applies to sby only.
            tool: "auto" | "sby" | "jaspergold" | "vc_formal". Auto uses config priority.
            timeout: Seconds before killing the tool. Default: 300.

        Returns a FormalResult dict:
            status: "PASS" | "FAIL" | "ERROR" | "UNKNOWN"
            rc: exit code (0=PASS, 2=FAIL, 16=ERROR for sby)
            failures: [{property, file, line}]
            traces: [path to counterexample VCD — open with launch_waveform]
            warnings: [{file, line, message}]
            errors: [{file, line, message}]
            workdir: work directory (persists so traces can be opened)
            raw_output: full tool log
        """
        if tool == "auto":
            chosen = pick("formal")
            tool = _FORMAL_ADAPTERS.get(chosen, "sby") if chosen else "sby"

        if tool == "sby":
            if sby_file:
                return sby_adapter.run(sby_file, timeout=timeout)

            if not files or not top:
                return _error_result("Provide either sby_file or both files + top.")

            sby_content = sby_adapter.generate_sby(
                files=files, top=top, mode=mode, depth=depth, engine=engine,
            )
            tmp_dir = Path(tempfile.mkdtemp(prefix="silica_sby_gen_"))
            sby_path = tmp_dir / f"{top}.sby"
            sby_path.write_text(sby_content, encoding="utf-8")
            result = sby_adapter.run(str(sby_path), timeout=timeout)
            result["generated_sby"] = sby_content
            return result

        elif tool == "jaspergold":
            return jaspergold.run(
                sby_file=sby_file, files=files, top=top,
                mode=mode, depth=depth, timeout=timeout,
            )

        elif tool == "vc_formal":
            return vc_formal.run(
                sby_file=sby_file, files=files, top=top,
                mode=mode, depth=depth, timeout=timeout,
            )

        else:
            return _error_result(
                f"Unknown formal tool '{tool}'. Supported: auto, sby, jaspergold, vc_formal."
            )


def _error_result(message: str) -> dict:
    return {
        "status": "ERROR",
        "rc": -1,
        "failures": [],
        "traces": [],
        "warnings": [],
        "errors": [{"file": "", "line": 0, "message": message}],
        "workdir": "",
        "raw_output": "",
    }
