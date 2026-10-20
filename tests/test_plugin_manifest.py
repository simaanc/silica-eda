"""Consistency checks for the plugin, marketplace and MCP registry files."""

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
    plugin = _json("plugin/.claude-plugin/plugin.json")
    assert plugin["version"] == pyproject["project"]["version"], (
        "plugin.json version must match pyproject.toml; run scripts/bump_version.py "
        "or update plugin/.claude-plugin/plugin.json")


def test_plugin_launches_the_published_server():
    server = _json("plugin/.mcp.json")["mcpServers"]["silica"]
    assert server == {"command": "uvx", "args": ["silica-eda@latest"]}


def test_marketplace_lists_this_plugin():
    plugin = _json("plugin/.claude-plugin/plugin.json")
    (entry,) = _json(".claude-plugin/marketplace.json")["plugins"]
    assert entry["name"] == plugin["name"] == "silica-eda"
    # Only plugin/ is copied into the user's plugin cache, not the repository.
    assert entry["source"] == "./plugin"
    assert (ROOT / "plugin" / "skills" / "silica" / "SKILL.md").is_file()
    # A version in both places makes Claude Code warn; plugin.json owns it.
    assert "version" not in entry


def test_registry_server_json_matches_the_package():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    server = _json("server.json")
    (package,) = server["packages"]
    version = pyproject["project"]["version"]
    assert server["version"] == package["version"] == version
    assert package["registryType"] == "pypi"
    assert package["identifier"] == pyproject["project"]["name"]
    # The registry checks the PyPI description (the README) for this line.
    readme = (ROOT / pyproject["project"]["readme"]).read_text(encoding="utf-8")
    assert f"mcp-name: {server['name']}" in readme
    assert len(server["description"]) <= 100  # the schema's limit
