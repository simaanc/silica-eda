"""Serial capture adapter — read a UART for a fixed time, optionally sending first.

Used to check what a freshly programmed board prints (a firmware banner, an
echo). Only the port the caller names is ever opened: the adapter never lists
or probes ports, since opening an unrelated serial device can reset or
confuse whatever is attached to it.

pyserial is an optional dependency (``pip install "silica-eda[serial]"``) and
is imported only when a capture runs.
"""

import errno
import getpass
import importlib
import importlib.util
import os
import re
import sys
import time

MAX_DURATION_S = 600.0


def _result(port: str, baud: int, expect: str | None, **fields) -> dict:
    base = {
        "port": port,
        "baud": baud,
        "elapsed_s": 0.0,
        "bytes_received": 0,
        "bytes_sent": 0,
        "lines": [],
        "text": "",
        "expect": expect,
        "matched": None,
        "match": None,
    }
    base.update(fields)
    return base


def _error(port: str, baud: int, expect: str | None, message: str,
           fix: str | None = None) -> dict:
    fields: dict = {"error": message}
    if fix:
        fields["fix"] = fix
    return _result(port, baud, expect, **fields)


def _permission_fix(port: str) -> str:
    """Commands that give the current user read/write access to ``port``."""
    if not sys.platform.startswith("linux"):
        return f"Give your user read and write access to {port}."
    user = getpass.getuser()
    target = os.path.realpath(port)
    fix = (f"sudo setfacl -m u:{user}:rw {target}   "
           "(temporary: lasts until the device is unplugged)")
    try:
        import grp
        group = grp.getgrgid(os.stat(target).st_gid).gr_name
    except (ImportError, KeyError, OSError):
        return fix
    if group != "root":
        fix += (f"; permanent: sudo usermod -aG {group} {user}, "
                "then log out and back in")
    return fix


def _preflight(port: str) -> tuple[str, str | None] | None:
    """Check a POSIX device path before opening it. Returns (error, fix) or None.

    Windows COM ports aren't filesystem paths, so they go straight to pyserial.
    """
    if sys.platform == "win32":
        return None
    if not os.path.exists(port):
        return (
            f"Serial port {port} does not exist.",
            "Check the board is connected and powered, then pass its port. "
            "On Linux the stable names are under /dev/serial/by-id/.",
        )
    if not os.access(port, os.R_OK | os.W_OK):
        return (f"No read/write permission on serial port {port}.",
                _permission_fix(port))
    return None


def _split_lines(chunks: list[tuple[float, bytes]]) -> list[dict]:
    """Split timestamped byte chunks into lines stamped with their first byte's time."""
    lines: list[dict] = []
    current = bytearray()
    started: float | None = None
    for t, chunk in chunks:
        for byte in chunk:
            if started is None:
                started = t
            if byte == 0x0A:
                text = current.decode("utf-8", errors="replace").rstrip("\r")
                lines.append({"t": round(started, 3), "text": text})
                current.clear()
                started = None
            else:
                current.append(byte)
    if current:
        text = current.decode("utf-8", errors="replace").rstrip("\r")
        lines.append({"t": round(started or 0.0, 3), "text": text, "partial": True})
    return lines


def run(
    port: str,
    baud: int = 115200,
    duration: float = 5.0,
    send: str | None = None,
    send_delay: float = 0.0,
    expect: str | None = None,
    stop_on_match: bool = True,
) -> dict:
    """Capture a serial port for ``duration`` seconds.

    Args:
        port: Device to open, e.g. "/dev/ttyUSB1" or "COM4". Required.
        baud: Baud rate (8N1, no flow control).
        duration: Seconds to listen, at most MAX_DURATION_S.
        send: Text to write (UTF-8) once ``send_delay`` seconds have passed.
        send_delay: Seconds to listen before sending.
        expect: Regex searched for in the captured text; sets ``matched``.
        stop_on_match: Stop as soon as ``expect`` matches instead of
            listening for the whole duration.
    """
    if not port or not isinstance(port, str):
        return _error(str(port), baud, expect, "No serial port given; pass its path.")
    if baud <= 0:
        return _error(port, baud, expect, f"Invalid baud rate {baud}.")
    if not 0 < duration <= MAX_DURATION_S:
        return _error(port, baud, expect,
                      f"duration must be between 0 and {MAX_DURATION_S:g} seconds.")
    if not 0 <= send_delay < duration:
        return _error(port, baud, expect, "send_delay must be at least 0 and less than duration.")
    pattern = None
    if expect is not None:
        try:
            pattern = re.compile(expect)
        except re.error as exc:
            return _error(port, baud, expect, f"Invalid expect regex: {exc}")

    if importlib.util.find_spec("serial") is None:
        return _error(port, baud, expect,
                      "pyserial is not installed in the server's Python environment.",
                      'pip install "silica-eda[serial]"')
    serial = importlib.import_module("serial")
    if not hasattr(serial, "Serial"):
        return _error(port, baud, expect,
                      "The installed 'serial' module is not pyserial.",
                      'pip uninstall serial && pip install "silica-eda[serial]"')

    problem = _preflight(port)
    if problem:
        return _error(port, baud, expect, *problem)

    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.05)
    except (serial.SerialException, OSError) as exc:
        code = getattr(exc, "errno", None)
        if code == errno.EACCES:
            return _error(port, baud, expect,
                          f"No read/write permission on serial port {port}.",
                          _permission_fix(port))
        if code == errno.EBUSY:
            return _error(port, baud, expect,
                          f"Serial port {port} is busy.",
                          "Close any other program using it, such as a serial terminal.")
        return _error(port, baud, expect, f"Could not open serial port {port}: {exc}")

    chunks: list[tuple[float, bytes]] = []
    received = bytearray()
    sent = 0
    did_send = send is None
    matched = None
    start = time.monotonic()
    try:
        with ser:
            ser.reset_input_buffer()
            while True:
                now = time.monotonic() - start
                if now >= duration:
                    break
                if not did_send and now >= send_delay:
                    sent = ser.write(send.encode("utf-8")) or 0
                    ser.flush()
                    did_send = True
                data = ser.read(max(1, ser.in_waiting))
                if data:
                    chunks.append((time.monotonic() - start, data))
                    received.extend(data)
                    if pattern and stop_on_match and pattern.search(
                            received.decode("utf-8", errors="replace")):
                        break
    except (serial.SerialException, OSError) as exc:
        return _error(port, baud, expect, f"Serial port {port} failed during capture: {exc}")
    elapsed = time.monotonic() - start

    text = received.decode("utf-8", errors="replace")
    match_text = None
    if pattern:
        m = pattern.search(text)
        matched = m is not None
        match_text = m.group(0) if m else None
    return _result(
        port, baud, expect,
        elapsed_s=round(elapsed, 3),
        bytes_received=len(received),
        bytes_sent=sent,
        lines=_split_lines(chunks),
        text=text,
        matched=matched,
        match=match_text,
    )
