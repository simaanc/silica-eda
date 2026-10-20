---
name: silica
description: Use for RTL and FPGA tasks (Verilog/SystemVerilog/VHDL lint, simulation, formal, synthesis, place and route, programming a board, reading its UART) with the silica MCP server's tools.
---

The silica MCP server sends its own instructions when it connects: the tool order, what each step passes to the next, and the known pitfalls. Follow those; this skill only points at them.

- Start with the `doctor` tool to see which EDA tools are installed and how to fix missing ones.
- Then follow the server's order: `lint` → `run_simulation` → `run_formal` → `synthesize` → `run_place_route` → `program_device` → `capture_serial`.
- For a failing simulation or proof, use the server's `debug_simulation_failure` or `debug_formal_failure` prompt.
- Always call `write_rtl` with `dry_run=True` first and show the diff before writing.
