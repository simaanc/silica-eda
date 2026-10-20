"""Tests for silica.doctor and the doctor MCP tool."""

import io
import json
import subprocess
import urllib.error
from unittest.mock import patch

import pytest
from conftest import MockMCP, make_proc

from silica import doctor
from silica.tools import doctor as doctor_tool


# First lines of real --version output (OSS CAD Suite 2026-10-14, Verible
# v0.0-4296, svlint 0.9.5).
@pytest.mark.parametrize("output,version", [
    ("Verilator 5.053 devel rev v5.052-403-g0dc5f722a (mod)", "5.053"),
    ("Icarus Verilog version 14.0 (devel) (s20260301-579-g15d870a52-dirty)", "14.0"),
    ("Yosys 0.70+16 (git sha1 3bb533450, Release, Clang 21.1.8)", "0.70+16"),
    ("SBY v0.69", "0.69"),
    ('"nextpnr-ice40" -- Next Generation Place and Route (Version nextpnr-0.11.1-63-g44a6c739)',
     "0.11.1-63-g44a6c739"),
    ("openFPGALoader v1.1.1", "1.1.1"),
    ("Version\tv0.0-4296-g0f262651", "0.0-4296-g0f262651"),
    ("svlint v0.9.5 rev:98e84ce9 rustc:1.91.0", "0.9.5"),
    ("no digits here", None),
])
def test_parse_version(output, version):
    assert doctor.parse_version(output) == version


def test_version_key():
    assert doctor.version_key("5.053") == (5, 53, 0)
    assert doctor.version_key("0.70+16") == (0, 70, 0)
    assert doctor.version_key("4.228") < doctor.version_key("5.002")


def _check(name):
    return next(c for c in doctor.CHECKS if c.name == name)


@patch("silica.doctor.oss_cad_suite.which", return_value=None)
def test_missing_tool_gets_install_hint(mock_which):
    entry = doctor._probe(_check("yosys"), timeout=1)
    assert entry["status"] == "missing" and entry["found"] is False
    assert entry["fix"] == doctor.install_hint("yosys")


@patch("silica.doctor.oss_cad_suite.which", return_value=None)
def test_missing_openxc7_tool_points_at_openxc7(mock_which):
    entry = doctor._probe(_check("nextpnr-xilinx"), timeout=1)
    assert "openXC7" in entry["fix"]


@patch("silica.doctor.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.doctor.subprocess.run", return_value=make_proc(stdout="Verilator 4.228 2022-10-01"))
@patch("silica.doctor.oss_cad_suite.which", return_value="/usr/bin/verilator")
def test_old_verilator_is_outdated(mock_which, mock_run, mock_env):
    entry = doctor._probe(_check("verilator"), timeout=1)
    assert (entry["status"], entry["version"]) == ("outdated", "4.228")
    assert "5.002" in entry["fix"] and "--binary" in entry["fix"]


@patch("silica.doctor.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.doctor.subprocess.run",
       side_effect=subprocess.TimeoutExpired(cmd=["yosys"], timeout=1))
@patch("silica.doctor.oss_cad_suite.which", return_value="/usr/bin/yosys")
def test_version_query_timeout_is_not_fatal(mock_which, mock_run, mock_env):
    entry = doctor._probe(_check("yosys"), timeout=1)
    assert entry["status"] == "found" and entry["version"] is None
    assert "failed" in entry["note"]


def _pypi(version):
    return io.BytesIO(json.dumps({"info": {"version": version}}).encode())


@patch("silica.doctor.__version__", "0.3.1")
def test_update_available(monkeypatch):
    monkeypatch.delenv("SILICA_NO_UPDATE_CHECK", raising=False)
    with patch("silica.doctor.urllib.request.urlopen", return_value=_pypi("0.4.0")):
        result = doctor.check_for_update()
    assert result["update_available"] is True and result["latest"] == "0.4.0"
    assert "uvx silica-eda@latest" in result["fix"]


@patch("silica.doctor.__version__", "0.4.0")
def test_up_to_date(monkeypatch):
    monkeypatch.delenv("SILICA_NO_UPDATE_CHECK", raising=False)
    with patch("silica.doctor.urllib.request.urlopen", return_value=_pypi("0.4.0")):
        result = doctor.check_for_update()
    assert result["update_available"] is False and "fix" not in result


def test_offline_update_check_fails_gracefully(monkeypatch):
    monkeypatch.delenv("SILICA_NO_UPDATE_CHECK", raising=False)
    with patch("silica.doctor.urllib.request.urlopen",
               side_effect=urllib.error.URLError("no network")):
        result = doctor.check_for_update()
    assert result == {"latest": None, "update_available": None,
                      "update_check": "unavailable (URLError)"}


def test_update_check_can_be_disabled(monkeypatch):
    monkeypatch.setenv("SILICA_NO_UPDATE_CHECK", "1")
    with patch("silica.doctor.urllib.request.urlopen") as urlopen:
        assert doctor.check_for_update()["update_check"] == "disabled"
    urlopen.assert_not_called()


@patch("silica.doctor.__version__", "0.0.0.dev0")
def test_dev_build_doesnt_claim_an_update(monkeypatch):
    monkeypatch.delenv("SILICA_NO_UPDATE_CHECK", raising=False)
    with patch("silica.doctor.urllib.request.urlopen", return_value=_pypi("0.4.0")):
        assert doctor.check_for_update()["update_available"] is None


def test_missing_extra_gets_pip_and_uvx_fixes():
    def version(dist):
        raise doctor.importlib.metadata.PackageNotFoundError(dist)

    with patch("silica.doctor.importlib.metadata.version", side_effect=version):
        extras = {e["name"]: e for e in doctor._extras()}
    assert extras["pyserial"]["installed"] is False
    assert 'silica-eda[serial]' in extras["pyserial"]["fix"]
    assert "uvx --with pyserial silica-eda@latest" in extras["pyserial"]["fix"]


@patch("silica.doctor.oss_cad_suite.find_root", return_value=None)
@patch("silica.doctor.subprocess.run")
@patch("silica.doctor.oss_cad_suite.which", return_value=None)
def test_report_never_runs_commercial_tools(mock_which, mock_run, mock_root):
    with patch("silica.detect.resolve",
               side_effect=lambda name: f"/opt/{name}" if name == "vcs" else None):
        report = doctor.report(check_updates=False)
    mock_run.assert_not_called()
    vcs = next(c for c in report["commercial"] if c["name"] == "vcs")
    assert vcs == {"name": "vcs", "category": "simulation", "found": True, "path": "/opt/vcs"}
    assert report["silica"]["update_check"] == "skipped"
    assert set(report["summary"]["missing"]) == {c.name for c in doctor.CHECKS}


def test_tool_passes_check_updates():
    mcp = MockMCP()
    doctor_tool.register(mcp)
    with patch("silica.doctor.report", return_value={"ok": 1}) as report:
        assert mcp.tools["doctor"](check_updates=False) == {"ok": 1}
    report.assert_called_once_with(check_updates=False)
