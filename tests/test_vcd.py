"""Tests for silica.vcd (pure-Python VCD parser)."""

import pytest

from silica import vcd

# A realistic icarus-style VCD: 4-bit counter with clock and reset.
COUNTER_VCD = """\
$date
    Wed Jul  1 12:00:00 2026
$end
$version
    Icarus Verilog
$end
$timescale
    1ns
$end
$scope module counter_tb $end
$var reg 1 ! clk $end
$var reg 1 " rst $end
$scope module dut $end
$var wire 1 ! clk $end
$var wire 1 " rst $end
$var reg 4 # count [3:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
$dumpvars
0!
1"
bx #
$end
#5
1!
#10
0!
#15
1!
#20
0!
0"
#25
1!
b1 #
#30
0!
#35
1!
b10 #
#40
0!
#45
1!
b11 #
"""


@pytest.fixture
def counter_vcd(tmp_path):
    f = tmp_path / "sim.vcd"
    f.write_text(COUNTER_VCD)
    return str(f)


def test_inventory_lists_all_signals(counter_vcd):
    r = vcd.parse(counter_vcd)
    names = [s["name"] for s in r["all_signals"]]
    assert "counter_tb.clk" in names
    assert "counter_tb.dut.count" in names
    assert r["timescale"] == "1ns"
    assert r["end_time"] == 45


def test_full_name_match(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["counter_tb.dut.count"])
    assert r["not_found"] == []
    assert len(r["signals"]) == 1
    assert r["signals"][0]["name"] == "counter_tb.dut.count"


def test_suffix_match(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["dut.count"])
    assert r["not_found"] == []
    assert r["signals"][0]["name"] == "counter_tb.dut.count"


def test_transitions_and_padding(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["dut.count"])
    tr = r["signals"][0]["transitions"]
    # initial x, then 0001 / 0010 / 0011 — padded to declared width,
    # x-extended per the IEEE rule
    assert tr[0] == {"time": 0, "value": "xxxx"}
    assert {"time": 25, "value": "0001"} in tr
    assert {"time": 35, "value": "0010"} in tr
    assert {"time": 45, "value": "0011"} in tr


def test_scalar_signal(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["counter_tb.rst"])
    tr = r["signals"][0]["transitions"]
    assert tr[0] == {"time": 0, "value": "1"}
    assert tr[1] == {"time": 20, "value": "0"}


def test_alias_ids_report_both_names(counter_vcd):
    # clk is dumped once but declared in two scopes with the same id
    r = vcd.parse(counter_vcd, signals=["counter_tb.clk", "counter_tb.dut.clk"])
    assert r["not_found"] == []
    names = {s["name"] for s in r["signals"]}
    assert names == {"counter_tb.clk", "counter_tb.dut.clk"}
    for s in r["signals"]:
        assert s["transitions"][0] == {"time": 0, "value": "0"}


def test_time_window_includes_state_at_start(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["dut.count"],
                  time_start=30, time_end=40)
    tr = r["signals"][0]["transitions"]
    # value before the window (0001 set at t=25) is clamped to window start
    assert tr[0] == {"time": 30, "value": "0001"}
    assert tr[1] == {"time": 35, "value": "0010"}
    assert all(30 <= t["time"] <= 40 for t in tr)


def test_max_transitions_truncates(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["counter_tb.clk"], max_transitions=3)
    sig = r["signals"][0]
    assert len(sig["transitions"]) == 3
    assert sig["truncated"] is True


def test_unknown_signal_reported(counter_vcd):
    r = vcd.parse(counter_vcd, signals=["dut.count", "bogus"])
    assert r["not_found"] == ["bogus"]
    assert len(r["signals"]) == 1


def test_not_a_vcd_raises(tmp_path):
    f = tmp_path / "junk.vcd"
    f.write_text("this is not a vcd file\n")
    with pytest.raises(ValueError):
        vcd.parse(str(f))


def test_values_packed_on_one_line(tmp_path):
    # The spec allows several value changes per line
    f = tmp_path / "packed.vcd"
    f.write_text(
        "$timescale 1ns $end\n"
        "$scope module tb $end\n"
        "$var reg 1 ! a $end\n"
        "$var reg 2 \" b $end\n"
        "$upscope $end\n"
        "$enddefinitions $end\n"
        "$dumpvars 0! b10 \" $end\n"
        "#10 1! b01 \"\n"
    )
    r = vcd.parse(str(f), signals=["tb.a", "tb.b"])
    by_name = {s["name"]: s["transitions"] for s in r["signals"]}
    assert by_name["tb.a"] == [{"time": 0, "value": "0"},
                               {"time": 10, "value": "1"}]
    assert by_name["tb.b"] == [{"time": 0, "value": "10"},
                               {"time": 10, "value": "01"}]
