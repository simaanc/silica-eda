"""cocotb adapter — build + run a Python (cocotb) testbench via cocotb's runner.

cocotb drives a real simulator (Icarus, Verilator, …) from Python coroutines.
Rather than run cocotb in-process (it mutates global/simulator state), we spawn
a short driver script in a subprocess with cocotb's runner API, then parse the
JUnit ``results.xml`` it writes. The module name is not imported here — only in
that subprocess — so the MCP server never loads user test code.
"""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from silica import oss_cad_suite
from silica.detect import resolve

# cocotb simulator id → the registry/binary name we detect for a friendly
# pre-flight error (cocotb would otherwise fail deep in its runner).
_SIM_BINARY = {
    "icarus": "iverilog",
    "verilator": "verilator",
    "ghdl": "ghdl",
    "questa": "questa",
    "xcelium": "xcelium",
    "vcs": "vcs",
}

# Driver executed in a subprocess. argv: sim toplevel module build_dir src...
_DRIVER = """\
import sys
try:
    from cocotb_tools.runner import get_runner  # cocotb >= 2.0
except ImportError:
    from cocotb.runner import get_runner  # cocotb 1.9

sim, toplevel, test_module, build_dir = sys.argv[1:5]
sources = sys.argv[5:]
runner = get_runner(sim)
runner.build(sources=sources, hdl_toplevel=toplevel, build_dir=build_dir,
             always=True)
runner.test(hdl_toplevel=toplevel, test_module=test_module, build_dir=build_dir)
"""


def run(
    sources: list[str],
    test_module: str,
    toplevel: str,
    simulator: str = "icarus",
    timeout: int = 120,
) -> dict:
    """Build and run a cocotb testbench.

    Args:
        sources: HDL design source files (absolute paths preferred).
        test_module: Path to the Python cocotb test file. Its directory is put
            on PYTHONPATH and the module is imported by name in the subprocess.
        toplevel: Top-level HDL module cocotb instantiates.
        simulator: cocotb simulator id — "icarus" | "verilator" | "ghdl" |
            "questa" | "xcelium" | "vcs".
        timeout: Seconds before killing the build+test subprocess.

    Returns a dict: {passed, failed, tests [{name, status, time, message}],
    simulator, raw_stdout, raw_stderr} or {"error": str}.
    """
    if importlib.util.find_spec("cocotb") is None:
        return {"error": (
            "cocotb is not installed in the server's Python environment. "
            "Install it with: pip install cocotb"
        )}

    bin_name = _SIM_BINARY.get(simulator)
    if bin_name is None:
        return {"error": (
            f"Unknown cocotb simulator '{simulator}'. Supported: "
            f"{', '.join(sorted(_SIM_BINARY))}."
        )}
    if not resolve(bin_name):
        return {"error": (
            f"cocotb simulator '{simulator}' needs '{bin_name}', which was not "
            f"found. Install it (or the OSS CAD Suite)."
        )}

    test_path = Path(test_module)
    if not test_path.is_file():
        return {"error": f"cocotb test module not found: {test_module}"}
    module_name = test_path.stem

    # cocotb finds the test module by importing it — put its dir on PYTHONPATH.
    env = oss_cad_suite.env_with_suite()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(test_path.parent) + (f"{_pathsep()}{existing_pp}" if existing_pp else "")
    )

    with tempfile.TemporaryDirectory(prefix="silica_cocotb_") as build_dir:
        driver = Path(build_dir) / "_silica_cocotb_driver.py"
        driver.write_text(_DRIVER)
        cmd = [
            sys.executable, str(driver),
            simulator, toplevel, module_name, build_dir,
            *[str(s) for s in sources],
        ]
        try:
            cp = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"cocotb run timed out after {timeout}s"}

        tests = _parse_results(Path(build_dir))
        passed = sum(1 for t in tests if t["status"] == "passed")
        failed = sum(1 for t in tests if t["status"] == "failed")

        result = {
            "simulator": simulator,
            "passed": passed,
            "failed": failed,
            "tests": tests,
            "raw_stdout": cp.stdout,
            "raw_stderr": cp.stderr,
        }
        # No results.xml and a nonzero exit means the build/elaboration failed
        # before any test ran — surface that rather than a silent 0/0.
        if not tests and cp.returncode != 0:
            detail = (cp.stderr or cp.stdout).strip()[-2000:]
            result["error"] = f"cocotb run failed before any test executed: {detail}"
        return result


def _pathsep() -> str:
    return ";" if sys.platform == "win32" else ":"


def _parse_results(build_dir: Path) -> list[dict]:
    """Parse cocotb's JUnit results.xml files under build_dir into test dicts."""
    tests: list[dict] = []
    for xml_file in sorted(build_dir.rglob("results.xml")):
        try:
            root = ElementTree.parse(xml_file).getroot()
        except ElementTree.ParseError:
            continue
        for case in root.iter("testcase"):
            failure = case.find("failure")
            error = case.find("error")
            bad = failure if failure is not None else error
            tests.append({
                "name": case.get("name", "?"),
                "status": "failed" if bad is not None else "passed",
                "time": float(case.get("time", "0") or "0"),
                "message": (bad.get("message", "") if bad is not None else ""),
            })
    return tests
