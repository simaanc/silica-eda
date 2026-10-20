"""Check a silica-eda build or release by talking to it over MCP.

    uv run python scripts/check_release.py --version 0.4.0 \\
        --server "uvx --refresh silica-eda==0.4.0" \\
        --expect-from "uv run silica serve"

Starts --server, checks that it reports --version, that it serves exactly the
tools the --expect-from server (normally the tagged source) serves, and, when
it has a doctor tool, that doctor runs without error. --retries covers PyPI
taking a little while to serve a just-published release. Exits non-zero on
any mismatch.
"""

import argparse
import asyncio
import json
import os
import shlex
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _session(command: str, call_doctor: bool) -> dict:
    argv = shlex.split(command)
    params = StdioServerParameters(command=argv[0], args=argv[1:], env={**os.environ})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        init = await s.initialize()
        tools = sorted(t.name for t in (await s.list_tools()).tools)
        doctor = None
        if call_doctor and "doctor" in tools:
            res = await s.call_tool("doctor", {}, read_timeout_seconds=120)
            doctor = {"is_error": res.is_error, "data": res.structured_content}
        return {"version": init.server_info.version, "tools": tools, "doctor": doctor}


def inspect(command: str, call_doctor: bool, timeout: float) -> dict:
    return asyncio.run(asyncio.wait_for(_session(command, call_doctor), timeout))


def compare(version: str, release: dict, expected_tools: list[str]) -> list[str]:
    """Return the problems found; an empty list means the release checks out."""
    problems = []
    if release["version"] != version:
        problems.append(f"server reports version {release['version']}, expected {version}")
    missing = sorted(set(expected_tools) - set(release["tools"]))
    extra = sorted(set(release["tools"]) - set(expected_tools))
    if missing:
        problems.append(f"tools missing from the release: {', '.join(missing)}")
    if extra:
        problems.append(f"tools not in the source: {', '.join(extra)}")
    doctor = release.get("doctor")
    if doctor is not None:
        data = doctor["data"] or {}
        if doctor["is_error"] or (isinstance(data, dict) and data.get("error")):
            problems.append(f"doctor failed: {json.dumps(data)[:500]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="version the server must report")
    parser.add_argument("--server", required=True, help="command that starts the server to check")
    parser.add_argument("--expect-from", required=True,
                        help="command that starts the reference server (the tagged source)")
    parser.add_argument("--retries", type=int, default=1,
                        help="attempts to start --server (default: 1)")
    parser.add_argument("--retry-delay", type=float, default=30.0,
                        help="seconds between attempts (default: 30)")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="seconds allowed per server session (default: 300)")
    args = parser.parse_args(argv)

    expected = inspect(args.expect_from, call_doctor=False, timeout=args.timeout)["tools"]
    release = None
    for attempt in range(1, args.retries + 1):
        try:
            release = inspect(args.server, call_doctor=True, timeout=args.timeout)
            break
        except Exception as exc:  # the server failing to start is the thing being retried
            print(f"attempt {attempt}/{args.retries}: could not start "
                  f"'{args.server}': {exc!r}", file=sys.stderr)
            if attempt < args.retries:
                time.sleep(args.retry_delay)
    if release is None:
        print("FAIL: the server never started", file=sys.stderr)
        return 1

    problems = compare(args.version, release, expected)
    for p in problems:
        print(f"FAIL: {p}", file=sys.stderr)
    if problems:
        return 1
    doctor = "ran" if release["doctor"] is not None else "not present"
    print(f"OK: silica-eda {release['version']} serves {len(release['tools'])} tools "
          f"matching the source; doctor {doctor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
