import os
import sys


def supports_hyperlinks() -> bool:
    if not sys.stdout.isatty():
        return False
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    colorterm = os.environ.get("COLORTERM", "").lower()
    supporting = {"iterm.app", "wezterm", "ghostty", "vscode", "hyper", "tabby"}
    if term_program in supporting:
        return True
    if "256color" in term and colorterm in ("truecolor", "24bit"):
        return True
    return False


def hyperlink(text: str, url: str) -> str:
    if supports_hyperlinks():
        return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
    return f"{text} ({url})"


def tool_link(name: str, tool: dict) -> str:
    return hyperlink(name, tool["url"])


def docs_link(tool: dict) -> str:
    return hyperlink("↗ docs", tool.get("docs", tool["url"]))
