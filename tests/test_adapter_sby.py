"""Tests for silica.adapters.sby."""

from unittest.mock import patch

import pytest
from conftest import make_proc

from silica.adapters import sby

SBY_PASS_OUTPUT = "DONE (PASS, rc=0)\n"
SBY_FAIL_OUTPUT = (
    "summary: failed assertion my_prop at dut.sv:42\n"
    "DONE (FAIL, rc=2)\n"
)
SBY_ERROR_OUTPUT = "DONE (ERROR, rc=16)\n"


@patch("silica.adapters.sby.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which):
    result = sby.run("check.sby")
    assert result["status"] == "ERROR"
    assert result["rc"] == -1


def test_file_not_found():
    result = sby.run("/nonexistent/path/check.sby")
    assert result["status"] == "ERROR"
    assert result["rc"] == -1
    assert "not found" in result["errors"][0]["message"].lower()


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_pass(mock_run, mock_which, mock_env, sby_file):
    mock_run.return_value = make_proc(stdout=SBY_PASS_OUTPUT, returncode=0)
    result = sby.run(sby_file)
    assert result["status"] == "PASS"
    assert result["rc"] == 0
    assert result["failures"] == []


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_fail(mock_run, mock_which, mock_env, sby_file):
    mock_run.return_value = make_proc(stdout=SBY_FAIL_OUTPUT, returncode=2)
    result = sby.run(sby_file)
    assert result["status"] == "FAIL"
    assert len(result["failures"]) == 1
    assert result["failures"][0]["property"] == "my_prop"
    assert result["failures"][0]["file"] == "dut.sv"
    assert result["failures"][0]["line"] == 42


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_error_status(mock_run, mock_which, mock_env, sby_file):
    mock_run.return_value = make_proc(stdout=SBY_ERROR_OUTPUT, returncode=16)
    result = sby.run(sby_file)
    assert result["status"] == "ERROR"


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run",
       side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=300))
def test_timeout(mock_run, mock_which, mock_env, sby_file):
    result = sby.run(sby_file)
    assert result["status"] == "UNKNOWN"
    assert "timed out" in result["errors"][0]["message"]


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_workdir_unique_across_same_stem_runs(mock_run, mock_which, mock_env, sby_file):
    # Two runs of the same .sby must not share a workdir, or the second
    # clobbers the first's traces. Workdir is the arg right after "-d".
    mock_run.return_value = make_proc(stdout=SBY_PASS_OUTPUT, returncode=0)

    def _workdir_of(call):
        cmd = call.args[0]
        return cmd[cmd.index("-d") + 1]

    sby.run(sby_file)
    sby.run(sby_file)
    workdirs = [_workdir_of(c) for c in mock_run.call_args_list]
    assert workdirs[0] != workdirs[1]


def test_generate_sby_contains_sections():
    content = sby.generate_sby(["dut.sv"], "top", mode="bmc", depth=10)
    assert "[options]" in content
    assert "mode bmc" in content
    assert "depth 10" in content
    assert "[engines]" in content
    assert "[script]" in content
    assert "[files]" in content
    assert "top" in content


def test_generate_sby_auto_engine_no_solver():
    with patch("silica.adapters.sby.oss_cad_suite.which", return_value=None):
        content = sby.generate_sby(["dut.sv"], "top", engine="auto")
        assert "smtbmc" in content


def test_generate_sby_auto_engine_with_solver():
    with patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/z3"):
        with patch("silica.adapters.sby._detect_solver", return_value="z3"):
            content = sby.generate_sby(["dut.sv"], "top", engine="auto")
            assert "smtbmc" in content


@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/z3")
def test_detect_solver_finds_z3(mock_which):
    solver = sby._detect_solver()
    assert solver == "z3"


@patch("silica.adapters.sby.oss_cad_suite.which", return_value=None)
def test_detect_solver_empty_when_none(mock_which):
    solver = sby._detect_solver()
    assert solver == ""


def test_generate_sby_rejects_duplicate_basenames():
    with pytest.raises(ValueError, match="Duplicate source basename"):
        sby.generate_sby(["a/dut.sv", "b/dut.sv"], "top")


def test_generate_sby_allows_repeated_same_path():
    # The same file listed twice is harmless — no clobber.
    content = sby.generate_sby(["dut.sv", "dut.sv"], "top")
    assert "[files]" in content


# sby 0.70 summaries, trimmed. {d} is the run's workdir.
SBY_UNKNOWN_INDUCTION_OUTPUT = """\
SBY 18:44:27 [{d}] summary: engine_0 (smtbmc z3) returned pass for basecase
SBY 18:44:27 [{d}] summary: engine_0 (smtbmc z3) returned FAIL for induction
SBY 18:44:27 [{d}] summary: counterexample trace [induction]: {d}/engine_0/trace_induct.vcd
SBY 18:44:27 [{d}] summary:   failed assertion top._witness_.check_assert_top_sv_65_18 \
at top.sv:65.13-65.35
SBY 18:44:27 [{d}] DONE (UNKNOWN, rc=4)
"""

SBY_FAIL_BOTH_OUTPUT = """\
SBY 18:39:02 [{d}] summary: engine_0 (smtbmc z3) returned FAIL for basecase
SBY 18:39:02 [{d}] summary: engine_0 (smtbmc z3) returned FAIL for induction
SBY 18:39:02 [{d}] summary: counterexample trace [basecase]: {d}/engine_0/trace.vcd
SBY 18:39:02 [{d}] summary:   failed assertion top._witness_.check_assert_top_sv_31_11 \
at top.sv:31.55-31.79 step 45
SBY 18:39:02 [{d}] summary: counterexample trace [induction]: {d}/engine_0/trace_induct.vcd
SBY 18:39:02 [{d}] summary:   failed assertion top._witness_.check_assert_top_sv_31_11 \
at top.sv:31.55-31.79
SBY 18:39:02 [{d}] DONE (FAIL, rc=2)
"""


def _traces_in(tmp_path):
    (tmp_path / "engine_0").mkdir()
    for name in ("trace.vcd", "trace_induct.vcd"):
        (tmp_path / "engine_0" / name).write_text("")
    return str(tmp_path)


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_unknown_induction_is_not_a_failure(mock_run, mock_which, mock_env, sby_file, tmp_path):
    d = _traces_in(tmp_path)
    mock_run.return_value = make_proc(
        stdout=SBY_UNKNOWN_INDUCTION_OUTPUT.format(d=d), returncode=4)
    result = sby.run(sby_file)
    assert result["status"] == "UNKNOWN"
    assert result["failures"] == []
    assert result["traces"] == []
    assert result["induction_failures"] == [
        {"property": "top._witness_.check_assert_top_sv_65_18", "file": "top.sv", "line": 65},
    ]
    assert result["induction_traces"] == [f"{d}/engine_0/trace_induct.vcd"]


@patch("silica.adapters.sby.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.sby.oss_cad_suite.which", return_value="/usr/bin/sby")
@patch("silica.adapters.sby.subprocess.run")
def test_fail_keeps_basecase_and_induction_apart(mock_run, mock_which, mock_env, sby_file,
                                                tmp_path):
    d = _traces_in(tmp_path)
    mock_run.return_value = make_proc(stdout=SBY_FAIL_BOTH_OUTPUT.format(d=d), returncode=2)
    result = sby.run(sby_file)
    assert result["status"] == "FAIL"
    assert [f["line"] for f in result["failures"]] == [31]
    assert result["traces"] == [f"{d}/engine_0/trace.vcd"]
    assert [f["line"] for f in result["induction_failures"]] == [31]
    assert result["induction_traces"] == [f"{d}/engine_0/trace_induct.vcd"]


@pytest.mark.parametrize("result", [
    sby._not_found(),
    sby.run("/nonexistent/path/check.sby"),
])
def test_error_results_carry_induction_keys(result):
    assert result["induction_failures"] == []
    assert result["induction_traces"] == []
