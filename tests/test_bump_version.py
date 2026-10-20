"""Tests for scripts/bump_version.py."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts" / "bump_version.py")
bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump)

CHANGELOG = """\
# Changelog

## [Unreleased]

### Added
- A thing.

## [0.3.1] - 2026-10-16

### Fixed
- Another thing.

[Unreleased]: https://github.com/simaanc/silica-eda/commits/main
[0.3.1]: https://pypi.org/project/silica-eda/0.3.1/
"""


@pytest.fixture
def repo(tmp_path):
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy(ROOT / "uv.lock", tmp_path / "uv.lock")
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    shutil.copy(ROOT / ".claude-plugin" / "plugin.json", plugin_dir / "plugin.json")
    shutil.copy(ROOT / "server.json", tmp_path / "server.json")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    return tmp_path


def _version(root):
    return bump.current_version((root / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("current,spec,expected", [
    ("0.3.1", "patch", "0.3.2"),
    ("0.3.1", "minor", "0.4.0"),
    ("0.3.1", "major", "1.0.0"),
    ("0.3.1", "0.10.0", "0.10.0"),
])
def test_next_version(current, spec, expected):
    assert bump.next_version(current, spec) == expected


@pytest.mark.parametrize("spec", ["0.3.1", "0.3.0", "0.4", "v0.4.0", "0.4.0rc1"])
def test_next_version_rejects_bad_or_old_versions(spec):
    with pytest.raises(bump.BumpError):
        bump.next_version("0.3.1", spec)


def test_bump_updates_all_files(repo, capsys):
    old = _version(repo)
    new = bump.next_version(old, "minor")
    assert bump.main([new, "--date", "2026-11-02", "--root", str(repo)]) == 0

    assert _version(repo) == new
    assert f'name = "silica-eda"\nversion = "{new}"' in (repo / "uv.lock").read_text()
    plugin = json.loads((repo / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == new
    server = json.loads((repo / "server.json").read_text())
    assert server["version"] == server["packages"][0]["version"] == new
    changelog = (repo / "CHANGELOG.md").read_text()
    assert f"## [Unreleased]\n\n## [{new}] - 2026-11-02\n\n### Added\n- A thing." in changelog
    assert f"[{new}]: https://pypi.org/project/silica-eda/{new}/" in changelog
    out = capsys.readouterr().out
    assert f"git tag -a v{new}" in out and f"git push origin v{new}" in out


def test_empty_unreleased_changes_nothing(repo, capsys):
    (repo / "CHANGELOG.md").write_text(
        CHANGELOG.replace("### Added\n- A thing.\n\n", ""), encoding="utf-8")
    before = {p: p.read_text() for p in repo.rglob("*") if p.is_file()}
    assert bump.main(["minor", "--root", str(repo)]) == 1
    assert "nothing to release" in capsys.readouterr().err
    assert {p: p.read_text() for p in repo.rglob("*") if p.is_file()} == before
