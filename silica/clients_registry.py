import os
import sys
import shutil
from pathlib import Path


def _home() -> Path:
    return Path.home()


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
        "detect_binary": None,
        "url": "https://claude.ai/download",
        "docs": "https://docs.claude.ai/",
        "restart_note": "Fully quit and relaunch Claude Desktop (Cmd+Q) after config update",
    },
    "claude_code": {
        "name": "Claude Code",
        "config_type": "command",
        "command_template": "claude mcp add silica {binary} serve",
        "detect_binary": "claude",
        "url": "https://docs.anthropic.com/en/docs/claude-code",
        "docs": "https://docs.anthropic.com/en/docs/claude-code/mcp",
        "restart_note": "Run the command above in your terminal — no restart needed",
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
        "detect_binary": "cursor",
        "url": "https://cursor.com",
        "docs": "https://docs.cursor.com/advanced/model-context-protocol",
        "restart_note": "Restart Cursor after config update",
    },
    "zed": {
        "name": "Zed",
        "config_type": "file",
        "config_key": "context_servers",
        "config_paths": {
            "darwin": _home() / ".config/zed/settings.json",
            "linux": _home() / ".config/zed/settings.json",
            "win32": _home() / "AppData/Roaming/Zed/settings.json",
        },
        "detect_binary": "zed",
        "url": "https://zed.dev",
        "docs": "https://zed.dev/docs/context-servers",
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
        "detect_binary": "windsurf",
        "url": "https://windsurf.com",
        "docs": "https://docs.windsurf.com/windsurf/mcp",
        "restart_note": "Restart Windsurf after config update",
    },
    "opencode": {
        "name": "OpenCode",
        "config_type": "file",
        "config_key": "mcp",
        "config_paths": {
            "darwin": _home() / ".config/opencode/config.json",
            "linux": _home() / ".config/opencode/config.json",
            "win32": _home() / "AppData/Roaming/opencode/config.json",
        },
        "detect_binary": "opencode",
        "url": "https://opencode.ai",
        "docs": "https://opencode.ai/docs/mcp",
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
        "detect_binary": "gemini",
        "url": "https://github.com/google-gemini/gemini-cli",
        "docs": "https://github.com/google-gemini/gemini-cli/blob/main/docs/mcp.md",
        "restart_note": "Restart Gemini CLI after config update",
    },
}
