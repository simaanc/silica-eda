"""Consistency checks for the Claude Code plugin and marketplace files."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_plugin_version_matches_pyproject():
    # Users get a plugin update only when this version changes, and
    # scripts/bump_version.py bumps both together.
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = _json(".claude-plugin/plugin.json")
    assert plugin["version"] == pyproject["project"]["version"], (
        "plugin.json version must match pyproject.toml; run scripts/bump_version.py "
        "or update .claude-plugin/plugin.json")


def test_plugin_launches_the_published_server():
    server = _json(".mcp.json")["mcpServers"]["silica"]
    assert server == {"command": "uvx", "args": ["silica-eda@latest"]}


def test_marketplace_lists_this_plugin():
    plugin = _json(".claude-plugin/plugin.json")
    (entry,) = _json(".claude-plugin/marketplace.json")["plugins"]
    assert entry["name"] == plugin["name"] == "silica-eda"
    assert entry["source"] == "./"
    # A version in both places makes Claude Code warn; plugin.json owns it.
    assert "version" not in entry
