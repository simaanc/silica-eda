"""OSS CAD Suite detection and binary resolution.

OSS CAD Suite (https://github.com/YosysHQ/oss-cad-suite-build) is a binary
distribution from YosysHQ that bundles most of the open-source EDA tools silica
wraps — verilator, iverilog, yosys, sby, surfer, gtkwave — plus the SMT solvers
sby needs (z3, bitwuzla, boolector, yices2).

silica does NOT download or install it: the bundle aggregates many tools under
their own licenses, so fetching/redistributing it is the user's call. Instead,
if the user has installed it, silica locates the suite's ``bin`` directory and
resolves bundled binaries from there *in addition to* PATH — so the tools work
even without sourcing the suite's ``environment`` script.

To point silica at a non-standard install location, set the ``oss_cad_suite.path``
key in ``~/.silica/config.toml`` or the ``SILICA_OSS_CAD_SUITE`` env var.
"""

import os
import shutil
import sys
from pathlib import Path

from silica import config as cfg

RELEASES_PAGE = "https://github.com/YosysHQ/oss-cad-suite-build/releases"

# Tools bundled in OSS CAD Suite (registry names). Used to decide whether a
# given tool can be satisfied by a detected suite install.
BUNDLED: frozenset[str] = frozenset(
    {"verilator", "iverilog", "yosys", "sby", "surfer", "gtkwave",
     "nextpnr", "ghdl", "eqy", "openfpgaloader"}
)

_root_cache: Path | None = None


def _looks_like_root(path: Path) -> bool:
    bindir = path / "bin"
    if not bindir.is_dir():
        return False
    return (bindir / "yosys").exists() or (bindir / "yosys.exe").exists()


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    # 1. explicit config
    recorded = cfg.load().get("oss_cad_suite", {}).get("path")
    if recorded:
        roots.append(Path(recorded).expanduser())
    # 2. env overrides
    for var in ("SILICA_OSS_CAD_SUITE", "OSS_CAD_SUITE", "OSS_CAD_SUITE_ROOT"):
        val = os.environ.get(var)
        if val:
            roots.append(Path(val).expanduser())
    # 3. common manual-install locations
    roots.append(Path.home() / "oss-cad-suite")
    roots.append(Path.home() / ".silica" / "oss-cad-suite")
    if sys.platform == "win32":
        system_drive = os.environ.get("SystemDrive", "C:")
        roots.append(Path(f"{system_drive}\\oss-cad-suite"))
    else:
        roots.append(Path("/opt/oss-cad-suite"))
        roots.append(Path("/usr/local/oss-cad-suite"))
    return roots


def find_root(refresh: bool = False) -> Path | None:
    """Return the suite root directory if one can be located, else None.

    Accepts either a directory that *is* a suite root or one that *contains*
    an ``oss-cad-suite`` subdirectory. Result is cached; pass refresh=True to
    re-scan."""
    global _root_cache
    if not refresh and _root_cache is not None and _looks_like_root(_root_cache):
        return _root_cache

    for cand in _candidate_roots():
        if _looks_like_root(cand):
            _root_cache = cand
            return cand
        nested = cand / "oss-cad-suite"
        if _looks_like_root(nested):
            _root_cache = nested
            return nested

    _root_cache = None
    return None


def bin_dir() -> Path | None:
    root = find_root()
    return (root / "bin") if root else None


def binary_path(name: str) -> str | None:
    """Return the path to ``name`` inside the suite's bin dir, or None."""
    bd = bin_dir()
    if not bd:
        return None
    for candidate in (name, f"{name}.exe", f"{name}.bat"):
        p = bd / candidate
        if p.exists():
            return str(p)
    return None


def is_installed() -> bool:
    return find_root() is not None


def set_path(path: str) -> Path | None:
    """Validate a user-supplied OSS CAD Suite location and record it in config.

    Accepts a directory that is a suite root or one that contains an
    ``oss-cad-suite`` subdir. On success, persists it to ``oss_cad_suite.path``
    in config, refreshes the cache, and returns the resolved root. Returns None
    if no suite is found at the given path."""
    p = Path(path).expanduser()
    for candidate in (p, p / "oss-cad-suite"):
        if _looks_like_root(candidate):
            data = dict(cfg.load())
            section = dict(data.get("oss_cad_suite", {}))
            section["path"] = str(candidate)
            data["oss_cad_suite"] = section
            cfg.save(data)
            find_root(refresh=True)
            return candidate
    return None


def which(binary: str) -> str | None:
    """``shutil.which`` with an OSS CAD Suite bin-dir fallback.

    Use this in adapters instead of ``shutil.which`` so a suite install that
    was never sourced onto PATH is still found."""
    return shutil.which(binary) or binary_path(binary)


def env_with_suite(base_env: dict | None = None) -> dict:
    """Return an environment dict with the suite's bin dir prepended to PATH.

    Pass this as ``env=`` to ``subprocess.run`` so a tool found in the suite
    can locate its siblings (e.g. sby → yosys → z3, or verilator → its bundled
    C++ compiler). A no-op when no suite is present."""
    env = dict(base_env if base_env is not None else os.environ)
    bd = bin_dir()
    if bd:
        env["PATH"] = str(bd) + os.pathsep + env.get("PATH", "")
    return env
