"""Prepare a release: bump the version and date the changelog.

    uv run python scripts/bump_version.py 0.4.0      # or: major | minor | patch

Updates the version in pyproject.toml, uv.lock and the Claude Code plugin
manifest (.claude-plugin/plugin.json), moves the "Unreleased"
changelog entries under a new "## [X.Y.Z] - YYYY-MM-DD" heading with a link,
and prints the commands to commit, open the release PR, then tag and push.
It changes files only; nothing is committed, tagged or pushed. See
RELEASING.md for the whole flow.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PYPROJECT_RE = re.compile(r'^(version = ")([^"]+)(")$', re.MULTILINE)
_LOCK_RE = re.compile(r'(name = "silica-eda"\nversion = ")([^"]+)(")')
_PLUGIN_RE = re.compile(r'^(  "version": ")([^"]+)(",?)$', re.MULTILINE)
_UNRELEASED = "## [Unreleased]\n"
_UNRELEASED_LINK_RE = re.compile(r"^\[Unreleased\]: .*$", re.MULTILINE)


class BumpError(Exception):
    pass


def parse(version: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(version)
    if not m:
        raise BumpError(f"'{version}' is not a MAJOR.MINOR.PATCH version")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def next_version(current: str, spec: str) -> str:
    """Resolve "major" / "minor" / "patch" or an explicit version against current."""
    major, minor, patch = parse(current)
    if spec == "major":
        return f"{major + 1}.0.0"
    if spec == "minor":
        return f"{major}.{minor + 1}.0"
    if spec == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if parse(spec) <= (major, minor, patch):
        raise BumpError(f"{spec} is not newer than the current version {current}")
    return spec


def current_version(pyproject: str) -> str:
    m = _PYPROJECT_RE.search(pyproject)
    if not m:
        raise BumpError("no version line found in pyproject.toml")
    return m.group(2)


def bump_pyproject(text: str, version: str) -> str:
    return _PYPROJECT_RE.sub(rf"\g<1>{version}\g<3>", text, count=1)


def bump_lock(text: str, version: str) -> str:
    new, n = _LOCK_RE.subn(rf"\g<1>{version}\g<3>", text, count=1)
    if n != 1:
        raise BumpError("no silica-eda package entry found in uv.lock")
    return new


def bump_plugin(text: str, version: str) -> str:
    new, n = _PLUGIN_RE.subn(rf"\g<1>{version}\g<3>", text, count=1)
    if n != 1:
        raise BumpError('no top-level "version" found in .claude-plugin/plugin.json')
    return new


def bump_changelog(text: str, version: str, date: str) -> str:
    """Start a "## [version] - date" section from the Unreleased entries."""
    start = text.find(_UNRELEASED)
    if start < 0:
        raise BumpError("CHANGELOG.md has no '## [Unreleased]' heading")
    body_start = start + len(_UNRELEASED)
    next_heading = text.find("\n## [", body_start)
    body = text[body_start:next_heading if next_heading >= 0 else len(text)]
    if not body.strip():
        raise BumpError("the Unreleased section is empty: nothing to release")
    text = (text[:body_start] + f"\n## [{version}] - {date}\n" + text[body_start:])
    link = f"[{version}]: https://pypi.org/project/silica-eda/{version}/"
    m = _UNRELEASED_LINK_RE.search(text)
    if m:
        text = text[:m.end()] + "\n" + link + text[m.end():]
    return text


def release_commands(version: str) -> str:
    tag = f"v{version}"
    return f"""\
Next steps (nothing has been committed, tagged or pushed):

  git switch -c release/{tag}
  git commit -s -am "chore: release {version}"
  git push -u origin release/{tag}
  gh pr create --base main --title "Release {version}" --fill

After the release PR is merged:

  git switch main && git pull --ff-only
  git tag -a {tag} -m "{tag}"
  git push origin {tag}

Pushing the tag runs the Publish workflow, which builds, publishes to PyPI
and then checks the release with `uvx silica-eda=={version}`."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help='new version, or "major", "minor" or "patch"')
    parser.add_argument("--date", default=datetime.date.today().isoformat(),
                        help="release date for the changelog (default: today)")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    pyproject_path = args.root / "pyproject.toml"
    lock_path = args.root / "uv.lock"
    plugin_path = args.root / ".claude-plugin" / "plugin.json"
    changelog_path = args.root / "CHANGELOG.md"
    try:
        pyproject = pyproject_path.read_text(encoding="utf-8")
        current = current_version(pyproject)
        version = next_version(current, args.version)
        new_pyproject = bump_pyproject(pyproject, version)
        new_lock = bump_lock(lock_path.read_text(encoding="utf-8"), version)
        new_plugin = bump_plugin(plugin_path.read_text(encoding="utf-8"), version)
        new_changelog = bump_changelog(
            changelog_path.read_text(encoding="utf-8"), version, args.date)
    except (BumpError, OSError) as exc:
        print(f"bump_version: {exc}", file=sys.stderr)
        return 1

    # Write only after every file has been prepared, so a failure leaves none half-done.
    pyproject_path.write_text(new_pyproject, encoding="utf-8")
    lock_path.write_text(new_lock, encoding="utf-8")
    plugin_path.write_text(new_plugin, encoding="utf-8")
    changelog_path.write_text(new_changelog, encoding="utf-8")
    print(f"silica-eda {current} -> {version}\n")
    print(release_commands(version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
