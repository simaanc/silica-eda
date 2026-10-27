"""Tests for scripts/release_notes.py."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "scripts" / "release_notes.py")
notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notes)

CHANGELOG = """\
# Changelog

## [Unreleased]

## [0.5.0] - 2026-10-20

### Added
- A thing.

## [0.4.0] - 2026-10-19

### Fixed
- Another thing.

[0.5.0]: https://pypi.org/project/silica-eda/0.5.0/
[0.4.0]: https://pypi.org/project/silica-eda/0.4.0/
"""


def test_middle_section_stops_at_next_heading():
    assert notes.section(CHANGELOG, "0.5.0") == "### Added\n- A thing."


def test_last_section_stops_at_link_references():
    assert notes.section(CHANGELOG, "0.4.0") == "### Fixed\n- Another thing."


def test_missing_version_fails():
    with pytest.raises(notes.NotesError, match=r"no '## \[0.6.0\]'"):
        notes.section(CHANGELOG, "0.6.0")


def test_empty_section_fails():
    with pytest.raises(notes.NotesError, match="empty"):
        notes.section(CHANGELOG.replace("### Added\n- A thing.\n", ""), "0.5.0")


def test_current_version_has_notes():
    import tomllib
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert notes.section((ROOT / "CHANGELOG.md").read_text(), version)
