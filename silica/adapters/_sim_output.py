"""Collect the waveform files a simulation run wrote to its working directory.

Simulations run in the DUT's directory, so relative paths in the testbench
($readmemh, $fopen) resolve the same way whether or not tracing is on. The
VCDs a run writes there are then moved to the run's persistent output dir.
"""

import shutil
from pathlib import Path


def snapshot(directory: str | Path, pattern: str = "*.vcd") -> dict[Path, int]:
    """Map each existing file matching pattern to its modification time."""
    return {p: p.stat().st_mtime_ns for p in Path(directory).glob(pattern)}


def move_written(
    directory: str | Path, before: dict[Path, int], dest: str | Path,
    pattern: str = "*.vcd",
) -> list[Path]:
    """Move files matching pattern that were created or rewritten since
    ``before`` into dest; return their new paths, sorted by name."""
    moved = []
    for p in sorted(Path(directory).glob(pattern)):
        if before.get(p) != p.stat().st_mtime_ns:
            target = Path(dest) / p.name
            shutil.move(str(p), target)
            moved.append(target)
    return moved
