"""SpyGlass adapter — Synopsys SpyGlass lint."""

import re
import subprocess
import tempfile
from pathlib import Path

from silica.adapters._script_paths import unsafe_script_value
from silica.detect import resolve

# SpyGlass violation format:
# filename.sv line 10 Violation <MSGID> message
# or: [MSGID]: filename.sv:10: message
_VIOL_RE = re.compile(
    r"^(\S+\.s?vh?)\s+line\s+(\d+)\s+Violation\s+<(\w+)>\s+(.+)$",
    re.MULTILINE,
)
_VIOL2_RE = re.compile(
    r"^\[(\w+)\]:\s*(\S+\.s?vh?):(\d+):\s*(.+)$",
    re.MULTILINE,
)
_MSG_RE = re.compile(r"^(Error|Warning):\s+(.+)$", re.MULTILINE)


def _parse_violations(output: str, file: str) -> list[dict]:
    results: list[dict] = []
    for m in _VIOL_RE.finditer(output):
        f, line, rule_id, message = m.groups()
        results.append({
            "file": f.strip(),
            "line": int(line),
            "severity": "warning",
            "rule_id": rule_id,
            "message": message.strip(),
        })
    for m in _VIOL2_RE.finditer(output):
        rule_id, f, line, message = m.groups()
        results.append({
            "file": f.strip(),
            "line": int(line),
            "severity": "warning",
            "rule_id": rule_id,
            "message": message.strip(),
        })
    return results


def _make_tcl(file: str, ruleset: str) -> str:
    goal = "lint/lint_rtl" if ruleset == "default" else f"lint/{ruleset}"
    return f"""\
read_file -type sverilog {{{file}}}
set_option enableSV yes
set_option language_version V2K
compile_design
current_methodology $SPYGLASS_HOME/GuideWare/latest/block/rtl_handoff
run_goal {goal}
report -rules
exit
"""


def run(
    file: str,
    ruleset: str = "default",
    timeout: int = 120,
) -> dict:
    """Lint a file with SpyGlass in batch mode."""
    bad = unsafe_script_value(file, ruleset)
    if bad:
        return {"warnings": [], "tool": "spyglass", "raw_output": "", "error": bad}

    binary = resolve("spyglass")
    if not binary:
        return _not_found()

    with tempfile.TemporaryDirectory(prefix="silica_sg_") as tmpdir:
        tcl_path = Path(tmpdir) / "run.tcl"
        tcl_path.write_text(_make_tcl(file, ruleset), encoding="utf-8")

        # Try sg_shell first (newer), fall back to spyglass -batch
        sg_shell = str(Path(binary).parent / "sg_shell")
        if not Path(sg_shell).exists():
            sg_shell = None

        if sg_shell:
            cmd = [sg_shell, "-tcl", str(tcl_path)]
        else:
            cmd = [binary, "-batch", "-tcl", str(tcl_path)]

        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
        )

    combined = cp.stdout + cp.stderr
    violations = _parse_violations(combined, file)

    # Also capture generic errors
    error_msgs = [
        {"file": "", "line": 0, "severity": "error", "message": m.group(2).strip()}
        for m in _MSG_RE.finditer(combined)
        if m.group(1) == "Error"
    ]

    return {
        "warnings": violations,
        "tool": "spyglass",
        "raw_output": combined,
        **({"error": "; ".join(e["message"] for e in error_msgs)} if error_msgs else {}),
    }


def _not_found() -> dict:
    return {
        "warnings": [],
        "tool": "spyglass",
        "raw_output": "",
        "error": "spyglass/sg_shell not found. SpyGlass requires a Synopsys license.",
    }
