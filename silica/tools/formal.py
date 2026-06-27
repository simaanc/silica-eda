"""MCP tool: run_formal."""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from silica.adapters import sby as sby_adapter
from silica.adapters import jaspergold, vc_formal, eqy as eqy_adapter
from silica.tools._config_dispatch import pick

_FORMAL_ADAPTERS = {
    "sby":        "sby",
    "eqy":        "eqy",
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
        gold_files: list[str] | None = None,
        gate_files: list[str] | None = None,
    ) -> dict:
        """Run formal verification or equivalence checking and return structured results.

        Two usage modes for property verification (sby/jaspergold/vc_formal):
          1. Pass sby_file — run an existing .sby or .tcl config file directly.
          2. Pass files + top — auto-generate a config and run it.

        For equivalence checking (tool="eqy"):
          1. Pass sby_file pointing to an .eqy config file.
          2. Pass gold_files + gate_files + top — auto-generate an .eqy config.

        Args:
            sby_file: Path to an existing config file (.sby, .eqy, or .tcl).
            files: RTL source files for property verification (when sby_file is omitted).
            top: Top module name.
            mode: "prove" | "bmc" | "cover" | "live". Default: "prove". (sby only)
            depth: Bound depth for bmc/prove. Default: 20. (sby only)
            engine: "auto" or explicit e.g. "smtbmc z3". (sby only)
            tool: "auto" | "sby" | "eqy" | "jaspergold" | "vc_formal".
                  Auto uses config priority order.
            timeout: Seconds before killing the tool. Default: 300.
            gold_files: Gold (reference) design files for equivalence checking (eqy only).
            gate_files: Gate (implementation) design files for equivalence checking (eqy only).

        Returns a FormalResult dict:
            status: "PASS" | "FAIL" | "ERROR" | "UNKNOWN"
            rc: exit code
            failures: [{property, file, line}]
            traces: [path to counterexample VCD — open with launch_waveform] (sby only)
            warnings, errors, workdir, raw_output
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

        elif tool == "eqy":
            return eqy_adapter.run(
                eqy_file=sby_file,
                gold_files=gold_files,
                gate_files=gate_files,
                top=top,
                timeout=timeout,
            )

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
                f"Unknown formal tool '{tool}'. Supported: auto, sby, eqy, jaspergold, vc_formal."
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
