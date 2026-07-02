"""silica setup — interactive first-run configuration wizard.
   silica config — read-only status viewer.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Raw keystroke reading is platform-specific. termios/tty are Unix-only;
# Windows uses msvcrt. Import lazily-but-at-top guarded by platform so the
# module imports cleanly everywhere.
if sys.platform == "win32":
    import msvcrt
else:
    import termios
    import tty

from silica import config as cfg
from silica import detect, oss_cad_suite
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

_CHECK = "✓ "
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
    if sys.platform == "win32":
        return _read_key_windows()
    return _read_key_unix()


def _read_key_unix() -> str:
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


def _read_key_windows() -> str:
    # Special keys (arrows) come as a two-byte sequence prefixed by \x00 or \xe0.
    # Map them to the ANSI escapes the rest of the widget already understands.
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        ch2 = msvcrt.getwch()
        return {
            "H": "\x1b[A",  # up
            "P": "\x1b[B",  # down
            "M": "\x1b[C",  # right
            "K": "\x1b[D",  # left
        }.get(ch2, "")
    if ch == "\x03":  # Ctrl-C
        raise KeyboardInterrupt
    return ch


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
    if sys.platform == "win32":
        return "windows"
    for pm in ("apt", "dnf", "pacman"):
        if shutil.which(pm):
            return pm
    return "apt"


_OS_READABLE = {"darwin": "macOS", "linux": "Linux", "windows": "Windows"}


def _os_availability(tool: dict) -> str | None:
    """Return a brief note if the tool doesn't support the current OS, else None."""
    plat = _platform_key()
    current = "windows" if plat == "win32" else plat  # normalise to os_support keys
    supported = tool.get("os_support", ["darwin", "linux", "windows"])
    if current not in supported:
        names = [_OS_READABLE.get(p, p) for p in supported]
        return "/".join(names) + " only"
    return None


# ── Tool / client detection ───────────────────────────────────────────────────

def _detect_tool(name: str) -> str | None:
    # Maps registry name (e.g. "questa") to its real binary ("vsim") before probing.
    return detect.resolve(name)


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
    cat_tools = {
        name: t for name, t in TOOLS.items()
        if t["category"] == category
    }
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
            avail = _os_availability(tool)
            if detected:
                meta = f"installed   {vendor} — {note}"
            else:
                avail_note = f"   ({avail})" if avail else ""
                meta = f"not found   {vendor} — {note}{avail_note}"

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
    print(f"\n  {_bold(client['name'])} — running: {_cyan(cmd)}")

    detect_bin = client.get("detect_binary")
    if detect_bin and not shutil.which(detect_bin):
        print(f"  {_dim(f'{detect_bin!r} not found in PATH — skipping.')}")
        print(f"  Run manually: {_cyan(cmd)}\n")
        return

    answer = input("  Run this command now? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        print(f"  {_dim('Skipped.')}  Run manually: {_cyan(cmd)}\n")
        return

    try:
        result = subprocess.run(cmd.split(), capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  {_green('Done.')}  {_dim(client['restart_note'])}\n")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    print(f"    {_dim(line)}")
        else:
            err = (result.stderr or result.stdout).strip()
            print(f"  {_YELLOW}Command failed (exit {result.returncode}){_RESET}")
            if err:
                for line in err.splitlines():
                    print(f"    {_dim(line)}")
            print(f"  Run manually: {_cyan(cmd)}\n")
    except Exception as e:
        print(f"  {_YELLOW}Could not run command: {e}{_RESET}")
        print(f"  Run manually: {_cyan(cmd)}\n")


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
        if detect.resolve(name):
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


def _collect_vendor_links(tool_names: list[str]) -> list[tuple[str, str]]:
    """Return [(display_name, url)] for selected commercial tools that aren't installed."""
    links = []
    for name in tool_names:
        tool = TOOLS.get(name)
        if not tool or tool["license"] != "commercial":
            continue
        if detect.resolve(name):
            continue
        vendor = tool.get("vendor", "commercial")
        url = tool.get("url", "")
        if url:
            links.append((f"{name} ({vendor})", url))
    return links


# ── Step 5: install hints ─────────────────────────────────────────────────────

def _step_install_hints(tool_selections: dict[str, list[str]]) -> None:
    all_names = [name for names in tool_selections.values() for name in names]

    missing_bundled = [
        n for n in all_names
        if n in oss_cad_suite.BUNDLED and not detect.resolve(n)
    ]

    if oss_cad_suite.is_installed():
        print(f"  {_green('OSS CAD Suite found')} at {oss_cad_suite.find_root()} "
              f"{_dim('— bundled tools will be used from there.')}\n")
    elif missing_bundled:
        # If the user already has the suite somewhere non-standard, let them
        # point silica at it now.
        print(f"  {_dim('OSS CAD Suite bundles: ' + ', '.join(missing_bundled) + '.')}")
        answer = input(
            "  Already have OSS CAD Suite installed? Enter its path "
            "(or leave blank to skip): "
        ).strip()
        if answer:
            root = oss_cad_suite.set_path(answer)
            if root:
                print(f"  {_green('Registered')} OSS CAD Suite at {root}\n")
            else:
                print(f"  {_YELLOW}No OSS CAD Suite found there "
                      f"(expected <path>/bin/yosys).{_RESET}\n")

    # Recompute after any manual registration above.
    lines = _collect_missing_hints(all_names)
    vendor_links = _collect_vendor_links(all_names)

    if not lines and not vendor_links:
        return

    if lines:
        print(_bold("Step 5 — Missing open-source tools — run to install:\n"))
        for line in lines:
            print(f"    {_cyan(line)}")

        # Tip: the tools the suite bundles can be installed together.
        still_missing = [
            n for n in all_names
            if n in oss_cad_suite.BUNDLED and not detect.resolve(n)
        ]
        if still_missing:
            joined = ", ".join(still_missing)
            print(f"\n  {_dim(f'Tip: {joined} are bundled together in OSS CAD Suite:')}")
            print(f"    {_cyan(oss_cad_suite.RELEASES_PAGE)}")

    if vendor_links:
        header = "\nStep 5 — Commercial tools selected but not found — contact vendor:\n" \
            if not lines else "\n  Commercial tools — contact vendor for access:\n"
        print(_bold(header) if not lines else _dim(header))
        for display_name, url in vendor_links:
            link = hyperlink(display_name, url) if supports_hyperlinks() else f"{display_name}:"
            print(f"    {link}")
            if not supports_hyperlinks():
                print(f"      {_cyan(url)}")

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

    print(_bold("Setup complete ✓\n"))
    print(f"  Tools enabled:      {tools_str}")
    print(f"  Clients configured: {clients_str}")
    print(f"  Config saved to:    {cfg.config_path()}\n")
    print("  Start the server:")
    print(f"    {_cyan('silica serve')}\n")
    print("  View current config anytime:")
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
            live = detect.resolve(name)
            mark = "✓" if live else "✗ (not installed)"
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
                mark = "✓" if detected else "✗"
                client_parts.append(f"{client['name']} {mark}")
        print(f"\n  {'MCP clients':<14} {'  '.join(client_parts)}")
    else:
        print(f"\n  {'MCP clients':<14} (none configured)")

    suite_root = oss_cad_suite.find_root()
    if suite_root:
        print(f"\n  {'OSS CAD Suite':<14} ✓ {suite_root}")
    else:
        hint = _dim("not detected — install it and silica will find it automatically")
        print(f"\n  {'OSS CAD Suite':<14} {hint}")

    all_enabled = [
        name
        for cat in CATEGORIES
        for name in data.get("tools", {}).get(cat, {}).get("enabled", [])
    ]
    hints = _collect_missing_hints(all_enabled)
    if hints:
        print(f"\n  {_bold('To install missing open-source tools:')}")
        for line in hints:
            print(f"    {_cyan(line)}")

    vendor_links = _collect_vendor_links(all_enabled)
    if vendor_links:
        print(f"\n  {_bold('Commercial tools not found — contact vendor:')}")
        for display_name, url in vendor_links:
            link = hyperlink(display_name, url) if supports_hyperlinks() else f"{display_name}:"
            print(f"    {link}")
            if not supports_hyperlinks():
                print(f"      {_cyan(url)}")

    print("\n  Run 'silica setup' to change configuration.\n")


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
