"""Reject values that would break out of generated tool scripts.

Adapters interpolate MCP-supplied file paths and identifiers (top module,
engine, ruleset, ...) into generated Yosys .ys commands, TCL scripts, and
sby/eqy config bodies. A quote, brace, bracket, dollar, semicolon, or
newline can escape its quoting context and inject tool commands, so such
values are rejected before any script text is built.
"""

_UNSAFE = set('"{}[]$;\n\r')


def unsafe_script_value(*values) -> str | None:
    """Return an error message if any value contains script metacharacters.

    Each argument may be a string or an iterable of strings; None entries
    are skipped. Returns None when everything is safe to interpolate.
    """
    for value in values:
        if value is None:
            continue
        items = [value] if isinstance(value, str) else value
        for item in items:
            if item is None:
                continue
            text = str(item)
            bad = next((ch for ch in text if ch in _UNSAFE), None)
            if bad is not None:
                return (
                    f"Refusing to build tool script: unsafe character {bad!r} "
                    f"in {text!r}"
                )
    return None
