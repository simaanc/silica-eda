"""Pure-Python VCD parsing for the read_waveform tool.

VCD is a plain-text format (IEEE 1800 §21.7), so no external tool is
needed — parsing it directly lets the model inspect signal values without
a human opening a waveform viewer.

The parser streams the file token-wise: headers may spread directives
across lines, and simulators are allowed to pack several value changes
onto one line (``$dumpvars 0! b0000 " $end``), so line-oriented parsing
is not enough.
"""

from pathlib import Path

_SCALAR_VALUES = "01xXzZ"


def _pad(value: str, width: int, var_type: str) -> str:
    """Left-extend a vector value to its declared width (IEEE rule: extend
    with the leftmost bit when it is x/z, otherwise with 0)."""
    if var_type == "real" or len(value) >= width:
        return value
    fill = value[0] if value[0] in "xz" else "0"
    return fill * (width - len(value)) + value


def _matches(full_name: str, requested: str) -> bool:
    """A request matches on the full hierarchical name or any trailing
    component boundary — "count" and "dut.count" both match
    "counter_tb.dut.count"."""
    return full_name == requested or full_name.endswith("." + requested)


def _parse_header(tokens: list[str]) -> tuple[str, list[dict], dict]:
    """Walk header tokens up to $enddefinitions.

    Returns (timescale, inventory, id_map) where id_map maps a VCD
    identifier code to the signal entries sharing it (aliases).
    """
    timescale = ""
    scope: list[str] = []
    inventory: list[dict] = []
    id_map: dict[str, list[dict]] = {}

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "$enddefinitions":
            break
        if t in ("$timescale", "$scope", "$upscope", "$var", "$comment",
                 "$date", "$version"):
            end = tokens.index("$end", i)
            body = tokens[i + 1:end]
            if t == "$timescale":
                timescale = "".join(body)
            elif t == "$scope" and len(body) >= 2:
                scope.append(body[1])
            elif t == "$upscope" and scope:
                scope.pop()
            elif t == "$var" and len(body) >= 4:
                var_type, width, ident, name = body[0], body[1], body[2], body[3]
                entry = {
                    "name": ".".join(scope + [name]),
                    "width": int(width),
                    "type": var_type,
                }
                inventory.append(entry)
                id_map.setdefault(ident, []).append(entry)
            i = end + 1
        else:
            i += 1
    return timescale, inventory, id_map


def parse(
    path: str,
    signals: list[str] | None = None,
    time_start: int | None = None,
    time_end: int | None = None,
    max_transitions: int = 200,
) -> dict:
    """Parse a VCD file and return transitions for the requested signals.

    Times are in raw VCD ticks; multiply by the returned timescale to get
    wall-clock time. When a time window is given, each signal's value just
    before the window is emitted as its first transition (clamped to
    time_start) so the state at window start is always known.

    Returns:
        {timescale, end_time, all_signals [{name, width}],
         signals [{name, width, transitions [{time, value}], truncated}],
         not_found [names]}
    Raises ValueError on a malformed header.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8", errors="replace") as f:
        header_tokens: list[str] = []
        for line in f:
            header_tokens.extend(line.split())
            if "$enddefinitions" in header_tokens:
                break
        else:
            raise ValueError("no $enddefinitions — not a VCD header")
        try:
            timescale, inventory, id_map = _parse_header(header_tokens)
        except ValueError as exc:
            raise ValueError(f"malformed VCD header: {exc}") from exc

        # Per requested-and-matched entry: transitions accumulate here.
        records: dict[int, dict] = {}
        watch: dict[str, list[dict]] = {}
        not_found: list[str] = []
        if signals:
            matched_entries: dict[int, dict] = {}
            for req in signals:
                hit = False
                for ident, entries in id_map.items():
                    for entry in entries:
                        if _matches(entry["name"], req):
                            hit = True
                            rec = matched_entries.get(id(entry))
                            if rec is None:
                                rec = {
                                    "name": entry["name"],
                                    "width": entry["width"],
                                    "type": entry["type"],
                                    "transitions": [],
                                    "truncated": False,
                                    "before_window": None,
                                }
                                matched_entries[id(entry)] = rec
                                watch.setdefault(ident, []).append(rec)
                if not hit:
                    not_found.append(req)
            records = matched_entries

        cur_time = 0
        end_time = 0
        past_window = False

        def record(ident: str, value: str) -> None:
            for rec in watch.get(ident, ()):
                val = _pad(value, rec["width"], rec["type"])
                if time_start is not None and cur_time < time_start:
                    rec["before_window"] = val
                    continue
                if time_end is not None and cur_time > time_end:
                    continue
                if rec["truncated"]:
                    continue
                if len(rec["transitions"]) >= max_transitions:
                    rec["truncated"] = True
                    continue
                rec["transitions"].append({"time": cur_time, "value": val})

        for line in f:
            tokens = line.split()
            k = 0
            while k < len(tokens):
                t = tokens[k]
                first = t[0]
                if first == "#":
                    cur_time = int(t[1:])
                    end_time = max(end_time, cur_time)
                    if time_end is not None and cur_time > time_end:
                        past_window = True
                elif first in "bBrR":
                    if k + 1 < len(tokens):
                        record(tokens[k + 1], t[1:].lower())
                        k += 1
                elif first in _SCALAR_VALUES:
                    record(t[1:], first.lower())
                # "$..." directives ($dumpvars, $end, ...) carry no value
                k += 1
            if past_window and watch:
                break

        result_signals = []
        for rec in records.values():
            transitions = rec["transitions"]
            if rec["before_window"] is not None and time_start is not None:
                if not transitions or transitions[0]["time"] > time_start:
                    transitions.insert(
                        0, {"time": time_start, "value": rec["before_window"]})
            result_signals.append({
                "name": rec["name"],
                "width": rec["width"],
                "transitions": transitions,
                "truncated": rec["truncated"],
            })
        result_signals.sort(key=lambda s: s["name"])

        return {
            "timescale": timescale,
            "end_time": end_time,
            "all_signals": [
                {"name": e["name"], "width": e["width"]} for e in inventory
            ],
            "signals": result_signals,
            "not_found": not_found,
        }
