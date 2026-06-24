from pathlib import Path

from mcp.server.fastmcp import FastMCP

_SKILLS_DIR = Path(__file__).parent / "skills"


def _load_skill(relative: str) -> str:
    path = _SKILLS_DIR / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


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


# --- register MCP tools ---

from silica.tools import formal, lint, project, simulation, synthesis  # noqa: E402

simulation.register(mcp)
synthesis.register(mcp)
lint.register(mcp)
formal.register(mcp)
project.register(mcp)
