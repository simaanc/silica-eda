"""Shared helper for resolving RTL source lists, including ``.f`` filelists.

Simulation, synthesis, and lint all take a set of source files. Real designs
span many files and are commonly captured in a filelist (``design.f``) — one
path per line. ``expand_sources`` flattens a mix of plain paths and filelists
into a single ordered, de-duplicated list so the tool layer can hand a clean
file list to any adapter.
"""

from pathlib import Path


def expand_sources(paths: list[str | None]) -> list[str]:
    """Flatten source paths, expanding any ``.f`` filelist in place.

    A ``.f`` / ``.F`` filelist holds one path per line; blank lines and comment
    lines (starting with ``//`` or ``#``) are skipped, and each listed path is
    resolved relative to the filelist's own directory. Simulator directive
    lines (starting with ``+`` such as ``+incdir+`` or ``-`` such as ``-y``)
    are not source files and are skipped. Plain (non-``.f``) paths pass through
    unchanged. Order is preserved and duplicates are dropped (first wins).

    A filelist that cannot be read raises ``FileNotFoundError`` / ``OSError`` —
    the caller surfaces it as a structured error.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(p: str) -> None:
        if p not in seen:
            seen.add(p)
            out.append(p)

    for path in paths:
        if not path:
            continue
        if Path(path).suffix.lower() == ".f":
            for entry in _read_filelist(Path(path)):
                _add(entry)
        else:
            _add(path)
    return out


def _read_filelist(filelist: Path) -> list[str]:
    base = filelist.parent
    entries: list[str] = []
    for raw in filelist.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "#", "+", "-")):
            continue
        candidate = Path(line)
        if not candidate.is_absolute():
            candidate = base / candidate
        entries.append(str(candidate))
    return entries
