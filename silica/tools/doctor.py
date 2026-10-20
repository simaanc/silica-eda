"""MCP tool: doctor."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica import doctor as doctor_report


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def doctor(check_updates: bool = True) -> dict:
        """Report silica's version and which EDA tools it can use, with a fix for each gap.

        Call this first in a new environment, or when a tool call says a tool
        is missing, to see what is installed before choosing a flow. It finds
        tools the same way the other tools do (PATH, then an OSS CAD Suite
        install) and asks each open-source tool for its version. Commercial
        tools (VCS, Questa, Xcelium, Vivado, ...) are only looked up, never
        run, so no license is checked out. Takes a few seconds.

        Args:
            check_updates: Also ask PyPI (3 s timeout) whether a newer
                silica-eda exists. Offline or blocked networks just report
                the check as unavailable. Set SILICA_NO_UPDATE_CHECK=1 to
                skip it everywhere.

        Returns:
            silica {version, latest, update_available, update_check, fix?},
            python, platform, executable, oss_cad_suite (path or None),
            tools [{name, used_by, found, path, version, min_version,
                    status: "ok" | "found" (version unknown) | "missing" |
                    "outdated", fix?, note?}],
            python_extras [{name, extra, used_by, installed, version, fix?}]
                (cocotb for run_cocotb, pyserial for capture_serial),
            commercial [{name, category, found, path}],
            summary {ok, missing, outdated} (tool names).
            Every missing or outdated entry carries a concrete "fix": an
            install command for this platform or the upgrade to make.
        """
        return doctor_report.report(check_updates=check_updates)
