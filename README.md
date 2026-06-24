# Silica

AI-native EDA environment — an MCP server that gives any LLM deep integration with the full EDA toolchain: simulation, synthesis, linting, formal verification, and autonomous debug loops.

## What it does

Silica wraps open source EDA tools (Verilator, Yosys, Verible, Icarus) in a structured MCP interface. You describe what you want to the model; Silica gives it the tool access and reasoning skills to find and fix RTL bugs, synthesize designs, and run verification workflows autonomously.

The core value: **closed autonomous loops**. Run sim → parse failure → reason about RTL → propose fix → re-run — without human copy-paste.

## Quick start

### 1. Install prerequisites

```bash
# macOS
brew install verilator yosys icarus-verilog

# Verible (linter) — grab the latest release binary
# https://github.com/chipsalliance/verible/releases
```

### 2. Install Silica

```bash
pip install silica
```

### 3. Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "silica": {
      "command": "silica",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Desktop. Silica loads automatically.

### 4. Test the UART example

Ask Claude:

> Run the UART TX simulation in examples/uart/ and tell me if it passes.

Or introduce a bug and ask Claude to find and fix it autonomously:

> In examples/uart/uart_tx.sv, change line 54 to use `==` instead of `== CLKS_PER_BIT - 1` for the baud counter comparison. Then run the simulation, find the bug, and fix it.

## MCP Tools (v0.1)

| Tool | Description |
|---|---|
| `run_simulation` | Simulate RTL (Verilator / Icarus). Returns structured errors. |
| `synthesize` | Synthesize to gates (Yosys). Returns utilization. |
| `lint` | Static analysis (Verible / Verilator). Returns structured warnings. |
| `read_rtl` | Read source file with line numbers. |
| `write_rtl` | Propose RTL changes — always dry_run=True before writing. |
| `get_project_structure` | Scan for RTL and constraint files. |
| `search_rtl` | Grep across project RTL with context. |
| `get_constraints` | Read constraint files (.xdc, .sdc, .lpf). |

## Workflow Skills

Silica ships reasoning scripts that teach the model how to interpret tool output and form hypotheses — not just how to call tools. Available as MCP prompts:

- `debug_simulation_failure` — step-by-step triage from error list to verified fix
- `write_testbench` — generate a complete testbench from a module interface
- `generate_assertions` — write SVA assertions from design intent
- `close_timing` — work through timing violations with synthesis feedback

## Architecture

```
silica/
├── silica/
│   ├── server.py          # FastMCP server; loads skills at boot
│   ├── cli.py             # silica serve entrypoint
│   ├── tools/             # MCP tool definitions
│   │   ├── simulation.py  # run_simulation()
│   │   ├── synthesis.py   # synthesize()
│   │   ├── lint.py        # lint()
│   │   └── project.py     # read_rtl(), write_rtl(), get_project_structure(), ...
│   ├── adapters/          # per-tool CLI wrappers + output parsers
│   │   ├── verilator.py
│   │   ├── icarus.py
│   │   ├── yosys.py
│   │   └── verible.py
│   └── skills/
│       ├── base/rtl_assistant.md         # always loaded
│       └── workflows/                    # loaded on demand
│           └── debug_simulation_failure.md
└── examples/
    └── uart/              # reference design for end-to-end testing
```

## Toolchain coverage (v0.1)

| Category | Tools |
|---|---|
| Simulation | Verilator (primary), Icarus Verilog (fallback) |
| Synthesis | Yosys (generic, ice40, ecp5, xilinx, gowin) |
| Linting | Verible (primary), Verilator lint-only (fallback) |

Commercial tools (VCS, Questa, Vivado, JasperGold) are post-MVP and will auto-activate when the binary is on PATH.

## Development

```bash
git clone https://github.com/getsilica/silica
cd silica
pip install -e ".[dev]"

# Run the server locally (for debugging)
silica serve

# Run the UART end-to-end test
iverilog -g2012 -o /tmp/uart_sim examples/uart/uart_tx_tb.sv examples/uart/uart_tx.sv
vvp /tmp/uart_sim
```

## License

silica is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only). You can use, modify and redistribute it, including commercially. If you distribute a modified version, or run one as a service that others interact with over a network, you must make your changes' source available under the same license.
