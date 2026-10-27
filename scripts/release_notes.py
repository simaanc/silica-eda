"""Print a version's CHANGELOG.md section, for the GitHub release body.

    uv run python scripts/release_notes.py 0.5.0

Prints the entries under "## [X.Y.Z] - YYYY-MM-DD", without the heading, and
fails if the changelog has no such section or it is empty. The Publish
workflow runs it in the build job, so a tag without changelog notes stops
before anything is uploaded, and again to create the GitHub release.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NotesError(Exception):
    pass


def section(changelog: str, version: str) -> str:
    """Return the body of the "## [version]" section, stripped."""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n", changelog, re.MULTILINE)
    if not m:
        raise NotesError(f"CHANGELOG.md has no '## [{version}]' section")
    end = re.search(r"^## \[|^\[[^\]]+\]: ", changelog[m.end():], re.MULTILINE)
    body = changelog[m.end():m.end() + end.start() if end else len(changelog)].strip()
    if not body:
        raise NotesError(f"the CHANGELOG.md section for {version} is empty")
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the release's MAJOR.MINOR.PATCH version")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        notes = section((args.root / "CHANGELOG.md").read_text(encoding="utf-8"), args.version)
    except (NotesError, OSError) as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
