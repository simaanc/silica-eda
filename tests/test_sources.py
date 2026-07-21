"""Tests for silica.tools._sources.expand_sources (.f filelist expansion)."""

import pytest

from silica.tools._sources import expand_sources


def test_plain_paths_pass_through():
    assert expand_sources(["a.sv", "b.sv"]) == ["a.sv", "b.sv"]


def test_none_and_empty_skipped():
    assert expand_sources([None, "", "a.sv"]) == ["a.sv"]


def test_dedup_preserves_first_occurrence():
    assert expand_sources(["a.sv", "b.sv", "a.sv"]) == ["a.sv", "b.sv"]


def test_filelist_expanded_relative_to_its_dir(tmp_path):
    (tmp_path / "adder.sv").write_text("module adder; endmodule\n")
    (tmp_path / "dut.sv").write_text("module dut; endmodule\n")
    fl = tmp_path / "design.f"
    fl.write_text("// design sources\nadder.sv\ndut.sv\n")

    result = expand_sources([str(fl)])
    assert result == [str(tmp_path / "adder.sv"), str(tmp_path / "dut.sv")]


def test_filelist_skips_comments_blanks_and_directives(tmp_path):
    fl = tmp_path / "d.f"
    fl.write_text(
        "\n"
        "# a hash comment\n"
        "// a slash comment\n"
        "+incdir+./include\n"
        "-y ./lib\n"
        "  real.sv  \n"
    )
    assert expand_sources([str(fl)]) == [str(tmp_path / "real.sv")]


def test_filelist_absolute_paths_kept(tmp_path):
    abs_path = tmp_path / "x.sv"
    fl = tmp_path / "d.f"
    fl.write_text(str(abs_path) + "\n")
    assert expand_sources([str(fl)]) == [str(abs_path)]


def test_filelist_mixed_with_plain_paths(tmp_path):
    fl = tmp_path / "d.f"
    fl.write_text("sub.sv\n")
    result = expand_sources(["top.sv", str(fl)])
    assert result == ["top.sv", str(tmp_path / "sub.sv")]


def test_missing_filelist_raises(tmp_path):
    with pytest.raises(OSError):
        expand_sources([str(tmp_path / "nope.f")])
