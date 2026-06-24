"""silica setup — interactive first-run configuration wizard.
   silica config — read-only status viewer.
"""

import json
import platform
import shutil
import sys
import termios
import tty
from pathlib import Path
from typing import Any

from silica import config as cfg
from silica.clients_registry import CLIENTS
from silica.terminal import docs_link, hyperlink, supports_hyperlinks, tool_link
from silica.tools_registry import CATEGORIES, TOOLS

# ── ANSI helpers ─────────────────────────────────────────────────────────────

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RESET = "\033[0m"
_UP = "\033[A"
_CLEAR_LINE = "\033[2K\r"

_CHECK = "✅"
_CIRCLE = "○ "


def _bold(s: str) -> str:
    return f"{_BOLD}{s}{_RESET}"


def _dim(s: str) -> str:
    return f"{_DIM}{s}{_RESET}"


def _green(s: str) -> str:
    return f"{_GREEN}{s}{_RESET}"


def _cyan(s: str) -> str:
    return f"{_CYAN}{s}{_RESET}"


# ── Raw keystroke reader ──────────────────────────────────────────────────────

def _read_key() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return f"\x1b[{ch3}"
            return "\x1b" + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Multi-select widget ───────────────────────────────────────────────────────

def multi_select(title: str, items: list[dict]) -> list[int]:
    """Render a checkbox list. Returns indices of selected items.

    Each item dict: {label: str, selected: bool, meta: str}
    Arrow keys navigate, space toggles, enter confirms, q/ctrl-c cancels.
    """
    selected = [i["selected"] for i in items]
    cursor = 0
    n = len(items)

    def _render(first: bool = False) -> None:
        if not first:
            # Move cursor up n+1 lines to redraw
            sys.stdout.write(f"\033[{n + 1}A")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(
            f"  {_bold(title)} "
            + _dim("(↑↓ navigate, space toggle, enter confirm)\n")
        )
        for i, item in enumerate(items):
            sys.stdout.write(_CLEAR_LINE)
            mark = _CHECK if selected[i] else _CIRCLE
            label = item["label"]
            meta = _dim(f"  {item['meta']}") if item.get("meta") else ""
            pointer = "→ " if i == cursor else "  "
            line = f"  {pointer}{mark} {label}{meta}\n"
            sys.stdout.write(line)
        sys.stdout.flush()

    _render(first=True)

    while True:
        key = _read_key()
        if key in ("\r", "\n"):
            break
        elif key == "\x1b[A":  # up
            cursor = (cursor - 1) % n
        elif key == "\x1b[B":  # down
            cursor = (cursor + 1) % n
        elif key == " ":
            selected[cursor] = not selected[cursor]
        elif key in ("\x03", "\x04", "q"):
            sys.stdout.write("\n")
            sys.exit(0)
        _render()

    sys.stdout.write("\n")
    return [i for i, s in enumerate(selected) if s]


# ── Platform detection ────────────────────────────────────────────────────────

def _platform_key() -> str:
    s = sys.platform  # "darwin" | "linux" | "win32"
    return s


def _pkg_manager() -> str:
    if sys.platform == "darwin":
        return "brew"
    for pm in ("apt", "dnf", "pacman"):
        if shutil.which(pm):
            return pm
    return "apt"


# ── Tool / client detection ───────────────────────────────────────────────────

def _detect_tool(name: str) -> str | None:
    return shutil.which(name)


def _detect_client(key: str) -> str | None:
    client = CLIENTS[key]
    if client.get("detect_binary"):
        path = shutil.which(client["detect_binary"])
        if path:
            return path
    # file-based detection
    paths = client.get("config_paths", {})
    plat = _platform_key()
    cfg_path = paths.get(plat)
    if cfg_path and Path(cfg_path).exists():
        return str(cfg_path)
    return None


# ── Banner ────────────────────────────────────────────────────────────────────

_BANNER = r"""
  ███████╗██╗██╗     ██╗ ██████╗ █████╗
  ██╔════╝██║██║     ██║██╔════╝██╔══██╗
  ███████╗██║██║     ██║██║     ███████║
  ╚════██║██║██║     ██║██║     ██╔══██║
  ███████║██║███████╗██║╚██████╗██║  ██║
  ╚══════╝╚═╝╚══════╝╚═╝ ╚═════╝╚═╝  ╚═╝
"""


def _print_banner() -> None:
    print(_cyan(_BANNER))
    site = hyperlink("getsilica.dev", "https://getsilica.dev")
    print(f"  {_bold('AI-native EDA environment')} — setup wizard")
    print(f"  {site}\n")


# ── Step 1: client selection ──────────────────────────────────────────────────

def _client_items(existing_clients: list[str]) -> list[dict]:
    items = []
    for key, client in CLIENTS.items():
        detected = _detect_client(key)
        label = hyperlink(client["name"], client["url"]) if supports_hyperlinks() else client["name"]
        if detected:
            meta = f"detected   {detected}"
        else:
            meta = "not found"
        preselected = key in existing_clients if existing_clients else bool(detected)
        items.append({"key": key, "label": label, "meta": meta, "selected": preselected})
    items.append({"key": "__other__", "label": "Other / manual", "meta": "", "selected": False})
    return items


def _step_clients(existing_clients: list[str]) -> list[str]:
    print(_bold("Step 1 — Which MCP client(s) are you using?"))
    items = _client_items(existing_clients)
    chosen = multi_select("MCP clients", items)
    result = []
    for i in chosen:
        key = items[i]["key"]
        if key != "__other__":
            result.append(key)
        else:
            result.append("__other__")
    return result


# ── Step 2: tool selection per category ──────────────────────────────────────

def _tool_items_for_category(category: str, existing_enabled: list[str]) -> list[dict]:
    items = []
    cat_tools = {name: t for name, t in TOOLS.items() if t["category"] == category}
    for name, tool in cat_tools.items():
        detected = _detect_tool(name)
        label_text = name
        if supports_hyperlinks():
            label_text = tool_link(name, tool) + "  " + docs_link(tool)
        else:
            label_text = f"{name}  ({tool['url']})"

        if tool["license"] == "open_source":
            if detected:
                meta = f"installed   {detected}"
            else:
                meta = "not found   open source"
        else:
            vendor = tool.get("vendor", "commercial")
            note = tool.get("note", "requires license")
            if detected:
                meta = f"installed   {vendor} — {note}"
            else:
                meta = f"not found   {vendor} — {note}"

        if existing_enabled:
            preselected = name in existing_enabled
        else:
            preselected = bool(detected)

        items.append({"name": name, "label": label_text, "meta": meta, "selected": preselected})
    return items


def _step_tools(existing_config: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for category in CATEGORIES:
        print(_bold(f"Step 2 — {category.capitalize()} tools:"))
        existing_enabled = (
            existing_config.get("tools", {}).get(category, {}).get("enabled", [])
        )
        items = _tool_items_for_category(category, existing_enabled)
        chosen = multi_select(f"{category.capitalize()} tools", items)
        selected_names = [items[i]["name"] for i in chosen]
        # priority: open source first, then commercial
        open_source = [n for n in selected_names if TOOLS[n]["license"] == "open_source"]
        commercial = [n for n in selected_names if TOOLS[n]["license"] == "commercial"]
        result[category] = open_source + commercial
    return result


# ── Step 3: persist config ────────────────────────────────────────────────────

def _build_config(tool_selections: dict[str, list[str]], client_selections: list[str]) -> dict:
    configured_clients = [c for c in client_selections if c != "__other__"]
    tools_section: dict[str, Any] = {}
    for category in CATEGORIES:
        enabled = tool_selections.get(category, [])
        tools_section[category] = {"enabled": enabled, "priority": enabled}
    return {
        "tools": tools_section,
        "clients": {"configured": configured_clients},
    }


# ── Step 4: client config injection ──────────────────────────────────────────

def _silica_binary() -> str:
    path = shutil.which("silica")
    if path:
        return path
    venv_bin = Path(sys.executable).parent / "silica"
    if venv_bin.exists():
        return str(venv_bin)
    return str(Path(sys.executable).parent / "silica")


def _merge_mcp_config(existing: dict, config_key: str, silica_bin: str) -> dict:
    result = dict(existing)
    block = result.setdefault(config_key, {})
    block["silica"] = {"command": silica_bin, "args": ["serve"]}
    return result


def _inject_file_client(key: str, silica_bin: str) -> None:
    client = CLIENTS[key]
    plat = _platform_key()
    config_path = client["config_paths"].get(plat)
    if not config_path:
        print(f"  {_dim('No config path for this platform, skipping.')}")
        return

    config_path = Path(config_path)
    existing: dict = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    config_key = client["config_key"]
    merged = _merge_mcp_config(existing, config_key, silica_bin)

    print(f"\n  {_bold(client['name'])} — will write to: {config_path}")
    preview = json.dumps({config_key: merged[config_key]}, indent=2)
    for line in preview.splitlines():
        print(f"    {line}")

    answer = input("\n  Write this config? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(merged, f, indent=2)
            f.write("\n")
        print(f"  {_green('Written.')}  {_dim(client['restart_note'])}\n")
    else:
        print(f"  {_dim('Skipped.')}\n")


def _inject_command_client(key: str, silica_bin: str) -> None:
    client = CLIENTS[key]
    cmd = client["command_template"].format(binary=silica_bin)
    print(f"\n  {_bold(client['name'])} — run this command:")
    print(f"    {_cyan(cmd)}")
    print(f"  {_dim(client['restart_note'])}\n")


def _inject_other(silica_bin: str) -> None:
    block = json.dumps({"command": silica_bin, "args": ["serve"]}, indent=2)
    setup_link = hyperlink("getsilica.dev/setup", "https://getsilica.dev/setup")
    print(f"\n  {_bold('Manual / Other MCP client')} — add this block to your client config:")
    for line in block.splitlines():
        print(f"    {line}")
    print(f"\n  For client-specific instructions see: {setup_link}\n")


def _step_inject_clients(client_selections: list[str]) -> None:
    if not client_selections:
        return
    print(_bold("Step 4 — Configuring MCP clients:"))
    silica_bin = _silica_binary()
    for key in client_selections:
        if key == "__other__":
            _inject_other(silica_bin)
        elif key not in CLIENTS:
            continue
        else:
            client = CLIENTS[key]
            if client["config_type"] == "file":
                _inject_file_client(key, silica_bin)
            elif client["config_type"] == "command":
                _inject_command_client(key, silica_bin)


# ── Install hint helpers ──────────────────────────────────────────────────────

def _collect_missing_hints(tool_names: list[str]) -> list[str]:
    """Return combined install hint lines for missing open source tools."""
    pm = _pkg_manager()
    plat = {"darwin": "darwin", "linux": "linux", "win32": "win32"}.get(sys.platform, "linux")
    raw: list[str] = []
    for name in tool_names:
        tool = TOOLS.get(name)
        if not tool or tool["license"] != "open_source":
            continue
        if shutil.which(name):
            continue
        install = tool.get("install", {})
        hint = install.get(pm) or install.get(plat) or next(iter(install.values()), None)
        if hint and hint not in raw:
            raw.append(hint)

    if not raw:
        return []

    groups: dict[str, list[str]] = {}
    solo: list[str] = []
    for hint in raw:
        parts = hint.split()
        if hint.startswith("#") or "&&" in hint or len(parts) < 3 or parts[-1].startswith("-"):
            solo.append(hint)
        else:
            prefix = " ".join(parts[:-1])
            groups.setdefault(prefix, []).append(parts[-1])

    lines = [prefix + " " + " ".join(pkgs) for prefix, pkgs in groups.items()]
    lines.extend(solo)
    return lines


# ── Step 5: install hints ─────────────────────────────────────────────────────

def _step_install_hints(tool_selections: dict[str, list[str]]) -> None:
    all_names = [name for names in tool_selections.values() for name in names]
    lines = _collect_missing_hints(all_names)
    if not lines:
        return
    print(_bold("Step 5 — Missing open source tools — run to install:\n"))
    for line in lines:
        print(f"    {_cyan(line)}")
    print()


# ── Step 6: summary ───────────────────────────────────────────────────────────

def _step_summary(tool_selections: dict[str, list[str]], client_selections: list[str]) -> None:
    all_tools = []
    for names in tool_selections.values():
        all_tools.extend(names)

    configured_clients = [
        CLIENTS[k]["name"] for k in client_selections if k in CLIENTS
    ]
    if "__other__" in client_selections:
        configured_clients.append("manual")

    tools_str = ", ".join(all_tools) if all_tools else "(none)"
    clients_str = ", ".join(configured_clients) if configured_clients else "(none)"

    serve_cmd = hyperlink("silica serve", "https://getsilica.dev")
    config_cmd = _bold("silica config")

    print(_bold("Setup complete ✅\n"))
    print(f"  Tools enabled:      {tools_str}")
    print(f"  Clients configured: {clients_str}")
    print(f"  Config saved to:    {cfg.config_path()}\n")
    print(f"  Start the server:")
    print(f"    {_cyan('silica serve')}\n")
    print(f"  View current config anytime:")
    print(f"    {_cyan('silica config')}\n")


# ── print_config ──────────────────────────────────────────────────────────────

def print_config() -> None:
    data = cfg.load()
    config_file = cfg.config_path()

    if not config_file.exists():
        print("  No config found. Run 'silica setup' to configure.")
        return

    print(f"\n  {_bold('Silica configuration')} — {config_file}\n")

    tools_section = data.get("tools", {})
    for category in CATEGORIES:
        cat_data = tools_section.get(category, {})
        enabled = cat_data.get("enabled", [])
        if not enabled:
            print(f"  {category.capitalize():<14} (none configured)")
            continue
        parts = []
        for name in enabled:
            live = shutil.which(name)
            mark = "✅" if live else "❌ (not installed)"
            parts.append(f"{name} {mark}")
        print(f"  {category.capitalize():<14} {'  '.join(parts)}")

    clients_section = data.get("clients", {})
    configured = clients_section.get("configured", [])
    if configured:
        client_parts = []
        for key in configured:
            client = CLIENTS.get(key)
            if client:
                detected = _detect_client(key)
                mark = "✅" if detected else "❌"
                client_parts.append(f"{client['name']} {mark}")
        print(f"\n  {'MCP clients':<14} {'  '.join(client_parts)}")
    else:
        print(f"\n  {'MCP clients':<14} (none configured)")

    all_enabled = [
        name
        for cat in CATEGORIES
        for name in data.get("tools", {}).get(cat, {}).get("enabled", [])
    ]
    hints = _collect_missing_hints(all_enabled)
    if hints:
        print(f"\n  {_bold('To install missing tools:')}")
        for line in hints:
            print(f"    {_cyan(line)}")

    print(f"\n  Run 'silica setup' to change configuration.\n")


# ── main entrypoint ───────────────────────────────────────────────────────────

def main() -> None:
    if not sys.stdin.isatty():
        print("silica setup requires an interactive terminal.")
        sys.exit(1)

    _print_banner()

    existing = cfg.load()
    existing_clients = existing.get("clients", {}).get("configured", [])

    # Step 1
    client_selections = _step_clients(existing_clients)
    print()

    # Step 2
    tool_selections = _step_tools(existing)
    print()

    # Step 3
    print(_bold("Step 3 — Saving configuration...\n"))
    new_config = _build_config(tool_selections, client_selections)
    cfg.save(new_config)
    print(f"  Saved to {cfg.config_path()}\n")

    # Step 4
    _step_inject_clients(client_selections)

    # Step 5
    _step_install_hints(tool_selections)

    # Step 6
    _step_summary(tool_selections, client_selections)
