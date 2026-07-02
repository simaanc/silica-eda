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

import atexit
import ctypes
import os
import shutil
import sys
import tempfile
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
_wrapper_dir: str | None = None  # cached temp dir with .bat wrappers for .exe.exe tools


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


def _short_path(path: str) -> str:
    """Return the Windows 8.3 short path for a long path, or the original on non-Windows."""
    if sys.platform != "win32":
        return path
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        buf = ctypes.create_unicode_buffer(32768)
        if kernel32.GetShortPathNameW(path, buf, len(buf)):
            return buf.value
    except Exception:
        pass
    return path


def _ensure_exe_wrappers(bin_dir: Path) -> str | None:
    """On Windows, create .bat wrappers in a temp dir for tools named *.exe.exe.

    OSS CAD Suite ships some tools as Python launcher + script pairs where the
    launcher is named ``tool.exe.exe`` and the script is ``tool.exe-script.py``.
    Both files are present but Windows can't resolve ``tool`` or ``tool.exe``
    from the shell. This function creates ``.bat`` files that call
    ``python3.exe <script>`` directly, bypassing the broken launchers."""
    global _wrapper_dir
    if sys.platform != "win32":
        return None
    if _wrapper_dir is not None:
        return _wrapper_dir or None

    python3 = bin_dir.parent / "lib" / "python3.exe"
    wrappers: list[tuple[str, str]] = []
    for double_exe in bin_dir.glob("*.exe.exe"):
        stem = Path(double_exe.stem).stem  # yosys-smtbmc.exe.exe → yosys-smtbmc
        script = bin_dir / f"{stem}.exe-script.py"
        if script.exists() and python3.exists():
            wrappers.append((stem, f'@"{python3}" "{script}" %*\n'))
        else:
            wrappers.append((stem, f'@"{double_exe}" %*\n'))

    if not wrappers:
        _wrapper_dir = ""
        return None

    d = tempfile.mkdtemp(prefix="silica_wrap_")
    atexit.register(shutil.rmtree, d, True)
    for stem, bat_content in wrappers:
        (Path(d) / f"{stem}.bat").write_text(bat_content)
    _wrapper_dir = d
    return d


def env_with_suite(base_env: dict | None = None) -> dict:
    """Return an environment dict with the suite's bin and lib dirs prepended to PATH.

    Pass this as ``env=`` to ``subprocess.run`` so a tool found in the suite
    can locate its siblings (e.g. sby → yosys → z3, or verilator → its bundled
    C++ compiler). On Windows the lib dir holds required DLLs. A no-op when no
    suite is present."""
    env = dict(base_env if base_env is not None else os.environ)
    root = find_root()
    if root:
        prepend = [str(root / "bin")]
        lib_dir = root / "lib"
        if lib_dir.is_dir():
            prepend.append(str(lib_dir))

        # On Windows, create .bat shims for tools with the .exe.exe naming quirk,
        # and set VERILATOR_ROOT via short path to avoid space-handling bugs.
        if sys.platform == "win32":
            wrapper = _ensure_exe_wrappers(root / "bin")
            if wrapper:
                prepend.insert(0, wrapper)
            verilator_share = root / "share" / "verilator"
            if verilator_share.is_dir() and "VERILATOR_ROOT" not in env:
                env["VERILATOR_ROOT"] = _short_path(str(verilator_share))

        env["PATH"] = os.pathsep.join(prepend) + os.pathsep + env.get("PATH", "")
    return env
