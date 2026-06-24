"""Load and save ~/.silica/config.toml."""

import tomllib
from pathlib import Path

_CONFIG_DIR = Path.home() / ".silica"
_CONFIG_PATH = _CONFIG_DIR / "config.toml"

_DEFAULTS: dict = {
    "tools": {
        "simulation": {"enabled": [], "priority": []},
        "synthesis": {"enabled": [], "priority": []},
        "formal": {"enabled": [], "priority": []},
        "lint": {"enabled": [], "priority": []},
        "waveform": {"enabled": [], "priority": []},
    },
    "clients": {"configured": []},
}


def load() -> dict:
    if not _CONFIG_PATH.exists():
        return _DEFAULTS
    try:
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return _DEFAULTS


def save(config: dict) -> None:
    import tomli_w

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump(config, f)


def config_path() -> Path:
    return _CONFIG_PATH
