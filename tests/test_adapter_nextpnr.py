"""Tests for silica.adapters.nextpnr."""

from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import make_proc

from silica.adapters import nextpnr

NEXTPNR_OUTPUT = """\
Info: Max frequency for clock 'clk': 72.45 MHz (PASS)
Info: LCs:          100/  7680     1%
Info: FFs:           50/  7680     0%
Warning: Unrouted net: unconnected_wire
"""

NEXTPNR_FAIL_OUTPUT = """\
Info: Max frequency for clock 'clk': 45.00 MHz (FAIL)
ERROR: Failed to place design
"""


# nextpnr-ice40: one report after placement, then the routed result.
NEXTPNR_PLACE_THEN_ROUTE = """\
Info: Max frequency for clock 'clk$SB_IO_IN_$glb_clk': 98.04 MHz (FAIL at 100.00 MHz)
Info: Routing..
Info: Max frequency for clock 'clk$SB_IO_IN_$glb_clk': 146.58 MHz (PASS at 100.00 MHz)
"""


def test_parse_timing_keeps_routed_report_per_clock():
    timing = nextpnr._parse_timing(NEXTPNR_PLACE_THEN_ROUTE)
    assert timing["clocks"] == [
        {"clock": "clk$SB_IO_IN_$glb_clk", "max_freq_mhz": 146.58, "pass": True},
    ]
    assert timing["failing_endpoints"] == 0


@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value=None)
def test_not_found(mock_which, netlist_file):
    result = nextpnr.run(netlist_file)
    assert result["exit_code"] == -1
    assert "nextpnr" in result["errors"][0]["message"].lower()


def test_netlist_not_found():
    result = nextpnr.run("/nonexistent/netlist.json")
    assert result["exit_code"] == -1
    assert "not found" in result["errors"][0]["message"].lower()


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_success_ice40(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout=NEXTPNR_OUTPUT, returncode=0)
    result = nextpnr.run(netlist_file, arch="ice40", device="hx8k")
    assert result["exit_code"] == 0
    assert result["tool"] == "nextpnr-ice40"
    assert len(result["warnings"]) == 1
    assert result["timing_summary"]["clocks"][0]["max_freq_mhz"] == pytest.approx(72.45)
    assert result["timing_summary"]["clocks"][0]["pass"] is True


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ecp5")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_success_ecp5(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout=NEXTPNR_OUTPUT, returncode=0)
    result = nextpnr.run(netlist_file, arch="ecp5", device="LFE5U-45F")
    assert result["exit_code"] == 0
    assert result["tool"] == "nextpnr-ecp5"


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_timing_fail(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout=NEXTPNR_FAIL_OUTPUT, returncode=1)
    result = nextpnr.run(netlist_file)
    assert result["timing_summary"]["clocks"][0]["pass"] is False
    assert len(result["errors"]) > 0


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run",
       side_effect=__import__("subprocess").TimeoutExpired(cmd=[], timeout=120))
def test_timeout(mock_run, mock_which, mock_env, netlist_file):
    result = nextpnr.run(netlist_file)
    assert result["exit_code"] == -1
    assert "timed out" in result["errors"][0]["message"]


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_output_path_resolved(mock_run, mock_which, mock_env, netlist_file, tmp_path):
    mock_run.return_value = make_proc(returncode=0)
    out = "relative_output.asc"
    nextpnr.run(netlist_file, output=out)
    # subprocess should have been called with an absolute path for output
    cmd = mock_run.call_args[0][0]
    asc_args = [a for a in cmd if "relative_output" in a]
    # the path passed should be absolute (resolved)
    from pathlib import Path
    if asc_args:
        assert Path(asc_args[0]).is_absolute()


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_cwd_is_workdir(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(returncode=0)
    nextpnr.run(netlist_file)
    call_kwargs = mock_run.call_args[1]
    assert "cwd" in call_kwargs
    assert call_kwargs["cwd"] is not None


def test_parse_timing_pass():
    raw = "Info: Max frequency for clock 'clk': 100.0 MHz (PASS)\n"
    timing = nextpnr._parse_timing(raw)
    assert len(timing["clocks"]) == 1
    assert timing["clocks"][0]["clock"] == "clk"
    assert timing["clocks"][0]["max_freq_mhz"] == pytest.approx(100.0)
    assert timing["clocks"][0]["pass"] is True
    assert timing["failing_endpoints"] == 0


def test_parse_timing_fail():
    raw = "Info: Max frequency for clock 'clk': 40.0 MHz (FAIL)\n"
    timing = nextpnr._parse_timing(raw)
    assert timing["clocks"][0]["pass"] is False
    assert timing["failing_endpoints"] == 1


def test_parse_utilization():
    raw = "Info: LCs:          100/  7680     1%\n"
    util = nextpnr._parse_utilization(raw)
    assert "LCs" in util
    assert util["LCs"]["used"] == 100
    assert util["LCs"]["total"] == 7680


@pytest.mark.parametrize("arch", ["ice40", "ecp5", "nexus", "machxo2", "generic"])
@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_all_arches(mock_run, mock_which, mock_env, arch, netlist_file):
    mock_run.return_value = make_proc(returncode=0)
    result = nextpnr.run(netlist_file, arch=arch)
    assert result["exit_code"] == 0


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value="/usr/bin/nextpnr-ice40")
@patch("silica.adapters.nextpnr.subprocess.run")
def test_unparseable_report_flagged(mock_run, mock_which, mock_env, netlist_file):
    mock_run.return_value = make_proc(stdout="some unrecognized output format", returncode=0)
    result = nextpnr.run(netlist_file)
    assert result["exit_code"] == 0
    assert any("raw_output" in w["message"] for w in result["warnings"])


# ---------------------------------------------------------------------------
# xilinx (openXC7 nextpnr-xilinx + fpga-as)
# ---------------------------------------------------------------------------

# Trimmed from openXC7 nextpnr 1.0.0 (himbaechel xilinx) on an xc7a100t.
NEXTPNR_XILINX_OUTPUT = """\
Warning: ignoring unsupported XDC option '-add' (on line 2)
Info: \t          SLICE_LUTX:     233/ 126800     0%
Info: \t           SLICE_FFX:      96/ 126800     0%
Info: Max frequency for clock '$techmap$auto$ff.cc:337:slice.C': 268.10 MHz (PASS at 100.00 MHz)
Info: Max frequency for clock '$techmap$auto$ff.cc:337:slice.C': 229.52 MHz (PASS at 100.00 MHz)
3 warnings, 0 errors
"""


@pytest.fixture
def xc7_env(tmp_path, monkeypatch):
    chipdb_dir = tmp_path / "chipdb"
    chipdb_dir.mkdir()
    (chipdb_dir / "xc7a100tcsg324.bin").write_bytes(b"")
    monkeypatch.setenv("ARTIX7_CHIPDB", str(chipdb_dir))
    monkeypatch.setenv("PRJXRAY_DB_DIR", str(tmp_path / "prjxray-db"))
    monkeypatch.delenv("NEXTPNR_XILINX_CHIPDB_DIR", raising=False)
    return chipdb_dir


def _fake_nextpnr_xilinx(cmd, **kwargs):
    """Stand-in for nextpnr-xilinx then fpga-as: write what each would."""
    if cmd[0].endswith("nextpnr-xilinx"):
        Path(cmd[cmd.index("--fasm") + 1]).write_text("# fasm\n")
        return make_proc(stdout=NEXTPNR_XILINX_OUTPUT, returncode=0)
    kwargs["stdout"].write(b"bitstream")
    return make_proc(stderr=b"", returncode=0)


def _which_all(name):
    return f"/usr/bin/{name}"


def test_xilinx_chipdb_lookup(xc7_env):
    assert nextpnr._xilinx_chipdb("xc7a100tcsg324-1") == xc7_env / "xc7a100tcsg324.bin"
    assert nextpnr._xilinx_chipdb("xc7a35tcsg324-1") is None
    direct = str(xc7_env / "xc7a100tcsg324.bin")
    assert nextpnr._xilinx_chipdb(direct) == Path(direct)


def test_xilinx_chipdb_from_nix_shell_dir(tmp_path, monkeypatch):
    (tmp_path / "xc7k325tffg676.bin").write_bytes(b"")
    monkeypatch.setenv("NEXTPNR_XILINX_CHIPDB_DIR", str(tmp_path))
    monkeypatch.delenv("KINTEX7_CHIPDB", raising=False)
    assert nextpnr._xilinx_chipdb("xc7k325tffg676-2") == tmp_path / "xc7k325tffg676.bin"


@patch("silica.adapters.nextpnr.oss_cad_suite.which", side_effect=_which_all)
def test_xilinx_missing_chipdb(mock_which, netlist_file, monkeypatch):
    for var in ("NEXTPNR_XILINX_CHIPDB_DIR", "ARTIX7_CHIPDB"):
        monkeypatch.delenv(var, raising=False)
    result = nextpnr.run(netlist_file, arch="xilinx", device="xc7a100tcsg324-1")
    assert result["exit_code"] == -1
    assert "chip database" in result["errors"][0]["message"]


@patch("silica.adapters.nextpnr.oss_cad_suite.which", return_value=None)
def test_xilinx_not_found_points_at_openxc7(mock_which, netlist_file):
    result = nextpnr.run(netlist_file, arch="xilinx", device="xc7a100tcsg324-1")
    assert "openXC7" in result["errors"][0]["message"]


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", side_effect=_which_all)
@patch("silica.adapters.nextpnr.subprocess.run", side_effect=_fake_nextpnr_xilinx)
def test_xilinx_place_route_and_assemble(mock_run, mock_which, mock_env, netlist_file,
                                         xc7_env, tmp_path):
    result = nextpnr.run(netlist_file, arch="xilinx", device="xc7a100tcsg324-1",
                         constraint="arty.xdc")
    assert result["exit_code"] == 0, result["errors"]
    assert result["tool"] == "nextpnr-xilinx"

    pnr_cmd = mock_run.call_args_list[0].args[0]
    assert pnr_cmd[pnr_cmd.index("--chipdb") + 1] == str(xc7_env / "xc7a100tcsg324.bin")
    assert pnr_cmd[pnr_cmd.index("--xdc") + 1].endswith("arty.xdc")
    assert "--device" not in pnr_cmd

    asm_cmd = mock_run.call_args_list[1].args[0]
    assert asm_cmd[0].endswith("fpga-as")
    assert f"--prjxray_db_path={tmp_path / 'prjxray-db' / 'artix7'}" in asm_cmd
    assert asm_cmd[asm_cmd.index("--part") + 1] == "xc7a100tcsg324-1"

    assert result["output"].endswith(".bit")
    assert Path(result["output"]).read_bytes() == b"bitstream"
    assert result["utilization"]["SLICE_LUTX"]["used"] == 233
    assert [c["max_freq_mhz"] for c in result["timing_summary"]["clocks"]] == [229.52]
    assert not any("FASM" in w["message"] for w in result["warnings"])


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which",
       side_effect=lambda name: None if name == "fpga-as" else f"/usr/bin/{name}")
@patch("silica.adapters.nextpnr.subprocess.run", side_effect=_fake_nextpnr_xilinx)
def test_xilinx_without_fpga_as_returns_fasm(mock_run, mock_which, mock_env, netlist_file,
                                             xc7_env):
    result = nextpnr.run(netlist_file, arch="xilinx", device="xc7a100tcsg324-1")
    assert result["exit_code"] == 0
    assert result["output"].endswith(".fasm")
    assert any("not a bitstream" in w["message"] for w in result["warnings"])
    assert mock_run.call_count == 1


@patch("silica.adapters.nextpnr.oss_cad_suite.env_with_suite", return_value={})
@patch("silica.adapters.nextpnr.oss_cad_suite.which", side_effect=_which_all)
@patch("silica.adapters.nextpnr.subprocess.run")
def test_xilinx_failed_assembly_leaves_no_bit(mock_run, mock_which, mock_env, netlist_file,
                                              xc7_env):
    def fake(cmd, **kwargs):
        if cmd[0].endswith("nextpnr-xilinx"):
            return _fake_nextpnr_xilinx(cmd, **kwargs)
        kwargs["stdout"].write(b"trunc")
        return make_proc(stderr=b"bad fasm line", returncode=1)
    mock_run.side_effect = fake
    result = nextpnr.run(netlist_file, arch="xilinx", device="xc7a100tcsg324-1")
    assert result["output"].endswith(".fasm")
    assert not (Path(result["workdir"]) / "out.bit").exists()
    assert any("fpga-as failed" in w["message"] for w in result["warnings"])
