"""Consistency checks for the plugin, marketplace and MCP registry files."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_plugin_has_no_version():
    # Without a version, Claude Code versions the plugin by commit SHA, so
    # users get plugin changes without a manual bump. A version here would pin
    # every user to it until someone changes the string.
    assert "version" not in _json("plugin/.claude-plugin/plugin.json")


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
    # The Publish workflow stamps both with the release version; they only
    # have to agree with each other here.
    assert server["version"] == package["version"]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == pyproject["project"]["name"]
    # The registry checks the PyPI description (the README) for this line.
    readme = (ROOT / pyproject["project"]["readme"]).read_text(encoding="utf-8")
    assert f"mcp-name: {server['name']}" in readme
    assert len(server["description"]) <= 100  # the schema's limit
