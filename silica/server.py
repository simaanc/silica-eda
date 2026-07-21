import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_SKILLS_DIR = Path(__file__).parent / "skills"

logger = logging.getLogger(__name__)


def _load_skill(relative: str) -> str:
    path = _SKILLS_DIR / relative
    if not path.exists():
        logger.warning("Registered skill file is missing: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


mcp = FastMCP(
    "silica",
    instructions=_load_skill("base/rtl_assistant.md"),
)

# --- workflow skills exposed as MCP prompts ---

@mcp.prompt()
def debug_simulation_failure() -> str:
    """Step-by-step reasoning script for triaging a failing simulation."""
    return _load_skill("workflows/debug_simulation_failure.md")


@mcp.prompt()
def write_testbench() -> str:
    """Reasoning script for generating a complete, useful testbench."""
    return _load_skill("workflows/write_testbench.md")


@mcp.prompt()
def generate_assertions() -> str:
    """Reasoning script for writing SVA assertions from design intent."""
    return _load_skill("workflows/generate_assertions.md")


@mcp.prompt()
def close_timing() -> str:
    """Step-by-step reasoning script for working through timing violations."""
    return _load_skill("workflows/close_timing.md")


@mcp.prompt()
def debug_formal_failure() -> str:
    """Reasoning script for triaging a formal FAIL/UNKNOWN via its counterexample."""
    return _load_skill("workflows/debug_formal_failure.md")


@mcp.prompt()
def cdc_review() -> str:
    """Reasoning script for reviewing clock domain crossings structurally."""
    return _load_skill("workflows/cdc_review.md")


# --- register MCP tools ---

from silica.tools import (  # noqa: E402
    formal,
    lint,
    place_route,
    program,
    project,
    simulation,
    synthesis,
    waveform,
)
from silica.tools import format as format_tool  # noqa: E402

simulation.register(mcp)
synthesis.register(mcp)
place_route.register(mcp)
program.register(mcp)
lint.register(mcp)
format_tool.register(mcp)
formal.register(mcp)
project.register(mcp)
waveform.register(mcp)
