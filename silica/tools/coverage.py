"""MCP tool: read_coverage."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

from silica.adapters import verilator


def _parse_lcov(info: str) -> tuple[list[dict], dict]:
    """Parse lcov ``.info`` text into per-file and overall line coverage.

    Recognises SF: (source file), DA:<line>,<hits>, and end_of_record. LF/LH
    totals in the file are ignored and recomputed from DA records so the result
    is correct even when a producer omits them. Repeated DA lines for one line
    number keep the maximum hit count.
    """
    files_raw: list[dict] = []
    cur: dict | None = None
    for line in info.splitlines():
        line = line.strip()
        if line.startswith("SF:"):
            cur = {"file": line[3:], "da": {}}
        elif line.startswith("DA:") and cur is not None:
            ln_str, _, cnt_str = line[3:].partition(",")
            try:
                ln, cnt = int(ln_str), int(cnt_str)
            except ValueError:
                continue
            cur["da"][ln] = max(cur["da"].get(ln, 0), cnt)
        elif line == "end_of_record" and cur is not None:
            files_raw.append(cur)
            cur = None
    if cur is not None:
        files_raw.append(cur)

    files: list[dict] = []
    tot_total = tot_covered = 0
    for f in files_raw:
        da = f["da"]
        total = len(da)
        covered = sum(1 for c in da.values() if c > 0)
        uncovered = sorted(ln for ln, c in da.items() if c == 0)
        tot_total += total
        tot_covered += covered
        files.append({
            "file": f["file"],
            "lines_total": total,
            "lines_covered": covered,
            "coverage_pct": round(100.0 * covered / total, 1) if total else 100.0,
            "uncovered_lines": uncovered,
        })

    overall = round(100.0 * tot_covered / tot_total, 1) if tot_total else 100.0
    total_summary = {
        "lines_total": tot_total,
        "lines_covered": tot_covered,
        "coverage_pct": overall,
    }
    return files, total_summary


def register(mcp: "MCPServer") -> None:
    @mcp.tool()
    def read_coverage(
        coverage_dat: str,
        max_uncovered: int = 50,
        timeout: int = 30,
    ) -> dict:
        """Summarize a Verilator coverage.dat as structured line coverage.

        Typical flow:
            1. result = run_simulation(..., simulator="verilator", coverage=True)
            2. read_coverage(result["coverage_dat"])   # find the weak spots

        Args:
            coverage_dat: Path to the coverage.dat produced by a coverage run
                          (the run_simulation result's coverage_dat field).
            max_uncovered: Cap on uncovered line numbers reported per file;
                           "uncovered_truncated" is set when the cap is hit.
            timeout: Seconds before killing verilator_coverage.

        Returns:
            {coverage, total {lines_total, lines_covered, coverage_pct},
             files [{file, lines_total, lines_covered, coverage_pct,
                     uncovered_lines, uncovered_truncated?}], file_count}
            or {"error": str} on failure.
        """
        path = Path(coverage_dat)
        if not path.is_file():
            return {"error": f"Coverage file not found: {coverage_dat}"}

        info = verilator.coverage_info(str(path), timeout=timeout)
        if "error" in info:
            return {"error": info["error"]}

        files, total = _parse_lcov(info["info"])
        for f in files:
            if len(f["uncovered_lines"]) > max_uncovered:
                f["uncovered_lines"] = f["uncovered_lines"][:max_uncovered]
                f["uncovered_truncated"] = True

        return {
            "coverage": coverage_dat,
            "total": total,
            "files": files,
            "file_count": len(files),
        }
