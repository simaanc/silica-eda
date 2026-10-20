"""Tests for the MCP client configs that `silica setup` writes."""

import json
from unittest.mock import patch

import pytest
from conftest import make_proc

from silica import setup
from silica.clients_registry import CLIENTS


@pytest.fixture
def client_path(tmp_path, monkeypatch):
    """Point every file client's config at a temp file on a "linux" host."""
    monkeypatch.setattr(setup, "_platform_key", lambda: "linux")
    paths = {}
    for key, client in CLIENTS.items():
        if client["config_type"] == "file":
            paths[key] = tmp_path / key / "config.json"
            monkeypatch.setitem(client, "config_paths", {"linux": paths[key]})
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    return paths


def test_every_client_launches_uvx_latest():
    for key, client in CLIENTS.items():
        if client["config_type"] == "command":
            assert client["command"][-3:] == ["--", "uvx", "silica-eda@latest"], key
        else:
            entry = setup._server_entry(client["entry"], "uvx")
            assert "serve" not in json.dumps(entry), key
            assert "silica-eda@latest" in json.dumps(entry), key


@pytest.mark.parametrize("key,expected", [
    ("claude_desktop", {"command": "/bin/uvx", "args": ["silica-eda@latest"]}),
    ("gemini_cli", {"command": "/bin/uvx", "args": ["silica-eda@latest"]}),
    ("windsurf", {"command": "/bin/uvx", "args": ["silica-eda@latest"]}),
    ("zed", {"command": "/bin/uvx", "args": ["silica-eda@latest"]}),
    ("cursor", {"type": "stdio", "command": "/bin/uvx", "args": ["silica-eda@latest"]}),
    ("opencode", {"type": "local", "command": ["/bin/uvx", "silica-eda@latest"],
                  "enabled": True}),
])
def test_file_client_entry_shape(client_path, key, expected):
    setup._inject_file_client(key, "/bin/uvx")
    written = json.loads(client_path[key].read_text())
    assert written == {CLIENTS[key]["config_key"]: {"silica": expected}}


def test_file_client_keeps_existing_settings(client_path):
    path = client_path["cursor"]
    path.parent.mkdir()
    path.write_text(json.dumps({
        "theme": "dark",
        "mcpServers": {"other": {"command": "x"}, "silica": {"command": "silica",
                                                            "args": ["serve"]}},
    }))
    setup._inject_file_client("cursor", "uvx")
    written = json.loads(path.read_text())
    assert written["theme"] == "dark"
    assert written["mcpServers"]["other"] == {"command": "x"}
    assert written["mcpServers"]["silica"]["args"] == ["silica-eda@latest"]


def test_file_client_without_documented_path_prints_block(client_path, monkeypatch,
                                                          capsys):
    # OpenCode documents no Windows path; Zed documents only Linux.
    monkeypatch.setattr(setup, "_platform_key", lambda: "win32")
    setup._inject_file_client("opencode", "uvx")
    out = capsys.readouterr().out
    assert '"silica-eda@latest"' in out
    assert not client_path["opencode"].exists()


def test_command_client_runs_claude_mcp_add(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    with patch("silica.setup.shutil.which", return_value="/usr/bin/claude"), \
         patch("silica.setup.subprocess.run", return_value=make_proc()) as run:
        setup._inject_command_client("claude_code")
    assert run.call_args.args[0] == [
        "claude", "mcp", "add", "--transport", "stdio", "--scope", "user",
        "silica", "--", "uvx", "silica-eda@latest",
    ]


def test_other_client_block_uses_uvx(capsys):
    setup._inject_other("uvx")
    out = capsys.readouterr().out
    assert '"command": "uvx"' in out
    assert '"silica-eda@latest"' in out
    assert '"serve"' not in out
