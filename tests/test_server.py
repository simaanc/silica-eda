"""Tests for silica.server: skill loading and prompt registration."""

import logging

import pytest

from silica import server


def test_load_skill_returns_content():
    text = server._load_skill("workflows/debug_simulation_failure.md")
    assert text.strip()


def test_load_skill_missing_returns_empty_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="silica.server"):
        text = server._load_skill("workflows/does_not_exist.md")
    assert text == ""
    assert any("missing" in rec.message.lower() for rec in caplog.records)


@pytest.mark.parametrize("prompt_fn", [
    server.debug_simulation_failure,
    server.write_testbench,
    server.generate_assertions,
    server.close_timing,
    server.debug_formal_failure,
    server.cdc_review,
])
def test_registered_prompts_return_content(prompt_fn):
    # Every registered MCP prompt must resolve to a real, non-empty skill file.
    assert prompt_fn().strip()


def test_base_skill_loaded_as_instructions():
    assert server.mcp is not None
    assert server._load_skill("base/rtl_assistant.md").strip()


def test_instructions_mention_every_tool_and_prompt():
    # The instructions are the one place a client reads the whole workflow;
    # a tool or prompt missing from them is invisible to that guidance.
    import asyncio

    text = server.mcp.instructions
    tools = [t.name for t in asyncio.run(server.mcp.list_tools())]
    prompts = [p.name for p in asyncio.run(server.mcp.list_prompts())]
    assert len(tools) >= 18
    missing = [name for name in tools + prompts if f"`{name}`" not in text]
    assert missing == []
