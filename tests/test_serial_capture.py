"""Tests for silica.adapters.serial_capture and the capture_serial tool.

A pty pair stands in for the board: the adapter opens the slave as a serial
port and a thread on the master side plays the firmware, so no hardware is
needed.
"""

import errno
import getpass
import os
import sys
import threading
import time
from unittest.mock import patch

import pytest
from conftest import MockMCP

from silica.adapters import serial_capture
from silica.tools import serial_capture as serial_capture_tool

serial = pytest.importorskip("serial")

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="needs a pty")


class FakeBoard(threading.Thread):
    """Writes ``script`` [(delay_s, bytes)] and echoes input like the SoC firmware."""

    def __init__(self, master: int, script: list[tuple[float, bytes]], echo: bool = True):
        super().__init__(daemon=True)
        self.master = master
        self.script = list(script)
        self.echo = echo
        self.received = bytearray()
        self.stop = threading.Event()

    def run(self):
        import select

        start = time.monotonic()
        while not self.stop.is_set():
            while self.script and time.monotonic() - start >= self.script[0][0]:
                os.write(self.master, self.script.pop(0)[1])
            ready, _, _ = select.select([self.master], [], [], 0.01)
            if ready:
                try:
                    data = os.read(self.master, 256)
                except OSError:
                    return
                self.received.extend(data)
                if self.echo:
                    os.write(self.master, data.replace(b"\r", b"\r\n"))


@pytest.fixture
def board():
    """Yield (port_path, start(script, echo)) for a pty-backed fake board."""
    import pty
    import tty

    master, slave = pty.openpty()
    tty.setraw(slave)  # no line-discipline echo before the port is opened
    threads: list[FakeBoard] = []

    def start(script, echo=True):
        t = FakeBoard(master, script, echo)
        t.start()
        threads.append(t)
        return t

    yield os.ttyname(slave), start
    for t in threads:
        t.stop.set()
        t.join(1)
    os.close(slave)
    os.close(master)


BANNER = b"\r\nSilica PicoRV32 SoC on Arty A7-100T\r\nclk=0x05f5e100 Hz; type to echo\r\n"


@posix_only
def test_captures_banner_with_timestamps(board):
    port, start = board
    start([(0.1, BANNER)])
    result = serial_capture.run(port, duration=2.0, expect=r"type to echo")
    assert "error" not in result, result
    assert result["matched"] is True
    assert result["match"] == "type to echo"
    assert result["bytes_received"] == len(BANNER)
    assert [line["text"] for line in result["lines"]] == [
        "", "Silica PicoRV32 SoC on Arty A7-100T", "clk=0x05f5e100 Hz; type to echo",
    ]
    assert all(0.05 <= line["t"] < 2.0 for line in result["lines"])
    # stop_on_match ends the capture as soon as the banner is in.
    assert result["elapsed_s"] < 1.5


@posix_only
def test_sends_and_reads_echo(board):
    port, start = board
    fake = start([(0.05, BANNER)])
    result = serial_capture.run(port, duration=2.0, send="hello silica\r",
                                send_delay=0.3, expect=r"hello silica\r\n")
    assert result["matched"] is True
    assert result["bytes_sent"] == len(b"hello silica\r")
    assert bytes(fake.received) == b"hello silica\r"
    assert result["lines"][-1]["text"] == "hello silica"
    assert result["lines"][-1]["t"] >= 0.3


@posix_only
def test_expect_not_found_listens_for_full_duration(board):
    port, start = board
    start([(0.05, b"booting\r\n")])
    result = serial_capture.run(port, duration=0.5, expect=r"PANIC")
    assert result["matched"] is False
    assert result["match"] is None
    assert result["elapsed_s"] >= 0.5
    assert result["lines"] == [{"t": result["lines"][0]["t"], "text": "booting"}]


@posix_only
def test_no_expect_leaves_matched_unset(board):
    port, start = board
    start([(0.05, b"no newline yet")])
    result = serial_capture.run(port, duration=0.4)
    assert result["matched"] is None
    assert result["lines"][-1]["text"] == "no newline yet"
    assert result["lines"][-1]["partial"] is True


# The existence check is POSIX-only: Windows COM ports aren't filesystem paths,
# so there the failure comes from pyserial (see the next test).
@posix_only
def test_missing_port_is_a_structured_error(tmp_path):
    port = str(tmp_path / "ttyUSB9")
    with patch.object(serial, "Serial") as opened:
        result = serial_capture.run(port, duration=1.0)
    opened.assert_not_called()
    assert "does not exist" in result["error"]
    assert result["fix"]
    assert result["lines"] == [] and result["bytes_received"] == 0


def test_open_failure_is_a_structured_error(tmp_path):
    # e.g. a COM port that doesn't exist on Windows: pyserial raises, no errno.
    port = tmp_path / "ttyUSB1"
    port.write_text("")
    failure = serial.SerialException("could not open port 'COM9': FileNotFoundError")
    with patch.object(serial, "Serial", side_effect=failure):
        result = serial_capture.run(str(port), duration=1.0)
    assert result["error"].startswith(f"Could not open serial port {port}")
    assert "COM9" in result["error"]
    assert result["lines"] == [] and result["bytes_received"] == 0


@pytest.mark.skipif(not sys.platform.startswith("linux") or os.geteuid() == 0,
                    reason="permission check needs a non-root Linux user")
def test_unreadable_port_suggests_setfacl(tmp_path):
    port = tmp_path / "ttyUSB1"
    port.write_text("")
    port.chmod(0)
    with patch.object(serial, "Serial") as opened:
        result = serial_capture.run(str(port), duration=1.0)
    opened.assert_not_called()
    assert "permission" in result["error"]
    user = getpass.getuser()
    assert result["fix"].startswith(f"sudo setfacl -m u:{user}:rw {os.path.realpath(port)}")


def test_busy_port_maps_to_error(tmp_path):
    port = tmp_path / "ttyUSB1"
    port.write_text("")
    busy = serial.SerialException(errno.EBUSY, "Device or resource busy")
    with patch.object(serial, "Serial", side_effect=busy):
        result = serial_capture.run(str(port), duration=1.0)
    assert "busy" in result["error"]
    assert "serial terminal" in result["fix"]


def test_pyserial_missing_gives_install_hint():
    real_find_spec = serial_capture.importlib.util.find_spec
    with patch.object(serial_capture.importlib.util, "find_spec",
                      side_effect=lambda name: None if name == "serial" else real_find_spec(name)):
        result = serial_capture.run("/dev/ttyUSB1", duration=1.0)
    assert "pyserial is not installed" in result["error"]
    assert result["fix"] == 'pip install "silica-eda[serial]"'


@pytest.mark.parametrize("kwargs,message", [
    ({"port": ""}, "No serial port"),
    ({"duration": 0}, "duration"),
    ({"duration": 601}, "duration"),
    ({"baud": 0}, "baud"),
    ({"expect": "("}, "Invalid expect regex"),
    ({"send": "x", "send_delay": 5.0, "duration": 1.0}, "send_delay"),
])
def test_bad_arguments(kwargs, message):
    args = {"port": "/dev/ttyUSB1", "duration": 1.0, **kwargs}
    result = serial_capture.run(**args)
    assert message in result["error"]


def test_split_lines_stamps_first_byte():
    lines = serial_capture._split_lines([(0.1, b"ab"), (0.2, b"c\r\nd"), (0.3, b"e\n")])
    assert lines == [{"t": 0.1, "text": "abc"}, {"t": 0.2, "text": "de"}]


def test_tool_passes_arguments_through():
    mcp = MockMCP()
    serial_capture_tool.register(mcp)
    with patch("silica.adapters.serial_capture.run", return_value={"ok": 1}) as run:
        result = mcp.tools["capture_serial"]("/dev/ttyUSB1", baud=9600, duration=2.0,
                                             send="x", expect="y")
    assert result == {"ok": 1}
    run.assert_called_once_with("/dev/ttyUSB1", baud=9600, duration=2.0, send="x",
                                send_delay=0.0, expect="y", stop_on_match=True)
