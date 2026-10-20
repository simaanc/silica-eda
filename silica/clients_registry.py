import json
import os
from pathlib import Path


def _home() -> Path:
    return Path.home()


# How every client starts the server: uv fetches the newest release from PyPI
# into a cached environment, so clients pick up new releases on restart.
SERVER_COMMAND = "uvx"
SERVER_ARGS = ["silica-eda@latest"]

# Config paths and entry shapes follow each client's documentation (the
# "docs" URL). A platform is left out when its docs don't give a path; the
# wizard then prints the block to add by hand. "entry" names the shape of the
# server entry: "stdio" is {"command", "args"}, "stdio_typed" adds
# "type": "stdio", "opencode" is OpenCode's {"type": "local", "command": [...]}.

CLIENTS = {
    "claude_desktop": {
        "name": "Claude Desktop",
        "config_type": "file",
        "config_key": "mcpServers",
        "config_paths": {
            "darwin": _home() / "Library/Application Support/Claude/claude_desktop_config.json",
            "linux": _home() / ".config/Claude/claude_desktop_config.json",
            "win32": Path(os.environ.get("APPDATA", "")) / "Claude/claude_desktop_config.json",
        },
        "entry": "stdio",
        "detect_binary": None,
        "url": "https://claude.ai/download",
        "docs": "https://modelcontextprotocol.io/docs/develop/connect-local-servers",
        "restart_note": "Fully quit and relaunch Claude Desktop (Cmd+Q) after config update",
    },
    "claude_code": {
        "name": "Claude Code",
        "config_type": "command",
        "command": ["claude", "mcp", "add", "--transport", "stdio", "--scope", "user",
                    "silica", "--", SERVER_COMMAND, *SERVER_ARGS],
        "detect_binary": "claude",
        "url": "https://code.claude.com/docs",
        "docs": "https://code.claude.com/docs/en/mcp",
        "restart_note": "Available in new Claude Code sessions",
    },
    "codex": {
        "name": "Codex CLI",
        "config_type": "command",
        "command": ["codex", "mcp", "add", "silica", "--", SERVER_COMMAND, *SERVER_ARGS],
        "detect_binary": "codex",
        "url": "https://developers.openai.com/codex/cli",
        "docs": "https://developers.openai.com/codex/mcp",
        "restart_note": ("Codex waits 10 s for a server to start by default; if the first "
                         "start times out while uv downloads silica, add "
                         "startup_timeout_sec = 60 under [mcp_servers.silica] in "
                         "~/.codex/config.toml"),
    },
    "vscode": {
        "name": "VS Code (Copilot)",
        "config_type": "command",
        "command": ["code", "--add-mcp", json.dumps({
            "name": "silica", "type": "stdio",
            "command": SERVER_COMMAND, "args": SERVER_ARGS,
        })],
        "detect_binary": "code",
        "url": "https://code.visualstudio.com",
        "docs": "https://code.visualstudio.com/docs/agents/reference/mcp-configuration",
        "restart_note": "Added to your VS Code user profile",
    },
    "cursor": {
        "name": "Cursor",
        "config_type": "file",
        "config_key": "mcpServers",
        "config_paths": {
            "darwin": _home() / ".cursor/mcp.json",
            "linux": _home() / ".cursor/mcp.json",
            "win32": _home() / ".cursor/mcp.json",
        },
        "entry": "stdio_typed",
        "detect_binary": "cursor",
        "url": "https://cursor.com",
        "docs": "https://cursor.com/docs/context/mcp",
        "restart_note": "Restart Cursor after config update",
    },
    "zed": {
        "name": "Zed",
        "config_type": "file",
        "config_key": "context_servers",
        # Zed documents only the Linux path; elsewhere use "zed: open settings".
        "config_paths": {
            "linux": _home() / ".config/zed/settings.json",
        },
        "entry": "stdio",
        "detect_binary": "zed",
        "url": "https://zed.dev",
        "docs": "https://zed.dev/docs/ai/mcp",
        "restart_note": "Restart Zed after config update",
    },
    "windsurf": {
        "name": "Windsurf",
        "config_type": "file",
        "config_key": "mcpServers",
        "config_paths": {
            "darwin": _home() / ".codeium/windsurf/mcp_config.json",
            "linux": _home() / ".codeium/windsurf/mcp_config.json",
            "win32": _home() / ".codeium/windsurf/mcp_config.json",
        },
        "entry": "stdio",
        "detect_binary": "windsurf",
        "url": "https://windsurf.com",
        "docs": "https://docs.devin.ai/windsurf/plugins/cascade/mcp",
        "restart_note": "Restart Windsurf after config update",
    },
    "opencode": {
        "name": "OpenCode",
        "config_type": "file",
        "config_key": "mcp",
        "config_paths": {
            "darwin": _home() / ".config/opencode/opencode.json",
            "linux": _home() / ".config/opencode/opencode.json",
        },
        "entry": "opencode",
        "detect_binary": "opencode",
        "url": "https://opencode.ai",
        "docs": "https://opencode.ai/docs/mcp-servers/",
        "restart_note": "Restart OpenCode after config update",
    },
    "gemini_cli": {
        "name": "Gemini CLI",
        "config_type": "file",
        "config_key": "mcpServers",
        "config_paths": {
            "darwin": _home() / ".gemini/settings.json",
            "linux": _home() / ".gemini/settings.json",
            "win32": _home() / ".gemini/settings.json",
        },
        "entry": "stdio",
        "detect_binary": "gemini",
        "url": "https://github.com/google-gemini/gemini-cli",
        "docs": "https://geminicli.com/docs/tools/mcp-server/",
        "restart_note": "Restart Gemini CLI after config update",
    },
}
