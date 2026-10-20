"""Tests for scripts/check_release.py's comparison logic."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_release", ROOT / "scripts" / "check_release.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

TOOLS = ["capture_serial", "lint", "synthesize"]


def _release(version="0.4.0", tools=TOOLS, doctor=None):
    return {"version": version, "tools": list(tools), "doctor": doctor}


def test_matching_release_passes():
    assert check.compare("0.4.0", _release(), TOOLS) == []


def test_version_mismatch():
    (problem,) = check.compare("0.4.0", _release(version="0.3.1"), TOOLS)
    assert "0.3.1" in problem and "0.4.0" in problem


def test_missing_and_extra_tools():
    problems = check.compare("0.4.0", _release(tools=["lint", "synthesize", "old_tool"]), TOOLS)
    assert problems == [
        "tools missing from the release: capture_serial",
        "tools not in the source: old_tool",
    ]


def test_doctor_error_fails_and_success_passes():
    ok = {"is_error": False, "data": {"silica": {"version": "0.4.0"}}}
    assert check.compare("0.4.0", _release(doctor=ok), TOOLS) == []
    bad = {"is_error": True, "data": {"error": "boom"}}
    (problem,) = check.compare("0.4.0", _release(doctor=bad), TOOLS)
    assert problem.startswith("doctor failed")
