<div align="center">

<img src="banner.png" alt="Silica" width="414"/>

**AI-native EDA environment** · MCP server for hardware design and verification

[![PyPI](https://img.shields.io/pypi/v/silica-eda?style=flat-square&color=3b82f6&label=pypi)](https://pypi.org/project/silica-eda/)
[![Python](https://img.shields.io/pypi/pyversions/silica-eda?style=flat-square)](https://pypi.org/project/silica-eda/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-22c55e?style=flat-square)](LICENSE)

</div>

---

## What it does

Silica wraps your EDA toolchain — open-source and commercial — in a structured MCP interface. You describe what you want to the model; Silica gives it the tool access and reasoning skills to find and fix RTL bugs, synthesize designs, and run verification workflows autonomously.

Open-source tools (Verilator, Yosys, Verible, SymbiYosys, Icarus, GHDL, nextpnr, eqy, openFPGALoader, Surfer) work out of the box. Commercial tools (VCS, Questa, Xcelium, Vivado, Quartus, DC Shell, JasperGold, VC Formal, SpyGlass, Verdi) are detected automatically when present on PATH — no extra config needed.

The core value: **closed autonomous loops**. Run sim → parse failure → reason about RTL → propose fix → re-run — without human copy-paste. The full open-source FPGA flow is covered end-to-end: synthesize → place and route → program device.

## Quick start

### 1. Install Silica

```bash
pip install silica-eda
```

### 2. Run the setup wizard

```bash
silica setup
```

The wizard detects which MCP clients and EDA tools you already have installed, lets you choose what to enable, and writes the MCP client config for you. It covers Claude Desktop, Claude Code, Cursor, Zed, Windsurf, OpenCode, and Gemini CLI.

When it's done, check your config anytime with:

```bash
silica config
```

### 3. Install missing tools (if any)

**Easiest path — OSS CAD Suite.** YosysHQ publishes a single binary bundle that includes Verilator, Icarus, Yosys, SymbiYosys, GHDL, nextpnr, eqy, openFPGALoader, Surfer, GTKWave, and all the SMT solvers. Download it from the [releases page](https://github.com/YosysHQ/oss-cad-suite-build/releases) and extract it — silica uses the bundled tools directly, with no PATH setup or `environment` sourcing needed. This covers everything except the linters (Verible / svlint), which you install separately.

> silica does **not** download OSS CAD Suite for you (it bundles many tools under their own licenses — that's your call to install). It only *detects* an existing install.

**How silica finds your OSS CAD Suite** — any one of these:

1. **Auto-detect** — common locations are checked automatically: `~/oss-cad-suite`, `~/.silica/oss-cad-suite`, `/opt/oss-cad-suite`, `/usr/local/oss-cad-suite` (Linux/macOS), or `C:\oss-cad-suite` (Windows).
2. **Enter a path in the wizard** — if it's installed somewhere else, `silica setup` prompts you for the path and remembers it.
3. **Set it manually** — point silica at any location with either:
   - the config key in `~/.silica/config.toml`:
     ```toml
     [oss_cad_suite]
     path = "/your/path/to/oss-cad-suite"
     ```
   - or the `SILICA_OSS_CAD_SUITE` environment variable:
     ```bash
     export SILICA_OSS_CAD_SUITE=/your/path/to/oss-cad-suite
     ```

   The path should point at the `oss-cad-suite` folder itself (the one containing `bin/`). Run `silica config` to confirm it's detected.

For anything not bundled in OSS CAD Suite, the wizard prints the exact install commands for your platform automatically.

### 4. Start the server

```bash
silica serve
```

Your MCP client will launch this automatically — you typically don't need to run it manually.

### 5. Test the UART example

Ask Claude:

> Run the UART TX simulation in examples/uart/ and tell me if it passes.

Or introduce a bug and ask Claude to find and fix it autonomously:

> In examples/uart/uart_tx.sv, change line 54 to use `==` instead of `== CLKS_PER_BIT - 1` for the baud counter comparison. Then run the simulation, find the bug, and fix it.

## Manual client setup

If you prefer to configure your MCP client by hand instead of using `silica setup`:

**Claude Desktop** — `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `~/.config/Claude/claude_desktop_config.json` (Linux):

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

**Claude Code**
```bash
claude mcp add silica silica serve
```

**Cursor** — `~/.cursor/mcp.json`:
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

**Windows (WSL2)**
```json
{
  "mcpServers": {
    "silica": {
      "command": "wsl",
      "args": ["-e", "silica", "serve"]
    }
  }
}
```

## CLI reference

| Command | Description |
|---|---|
| `silica serve` | Start the MCP server (stdio transport). Default if no subcommand given. |
| `silica setup` | Interactive first-run configuration wizard. |
| `silica config` | Show current configuration and live tool status (incl. detected OSS CAD Suite). |

## Controlling tool selection

By default every detected tool is available and `auto` picks the best one (open-source first). To control this per category, edit `~/.silica/config.toml`:

```toml
[tools.simulation]
priority = ["verilator", "iverilog"]   # ordering for auto-selection
enabled  = ["verilator", "iverilog"]   # allowlist — everything else is blocked
```

`priority` reorders what `auto` tries. `enabled` is an enforced allowlist: tools not on it can't be used **even when the model asks for one explicitly** — the request is rejected with an error naming the tool and what's enabled, so the model can retry with an allowed one. Useful when a machine has commercial tools installed that shouldn't be run (license pools, air-gapped flows). Leave `enabled` empty or unset for no restriction.

Categories: `simulation`, `synthesis`, `place_route`, `formal`, `lint`, `waveform`, `program`.

## Guardrails

Built for pointing an autonomous agent at a real repo:

- **File access is confined to the project directory** — `read_rtl` / `write_rtl` / `get_constraints` reject absolute or `..` paths that escape the directory the server was started in.
- **Writes are diff-first** — `write_rtl` defaults to a dry run that returns a unified diff; nothing touches disk until explicitly confirmed.
- **A hung tool never kills the server** — every tool call has a timeout and returns a structured error instead of crashing the session.

## MCP Tools

| Tool | Description |
|---|---|
| `run_simulation` | Simulate RTL. Auto-selects from Verilator, Icarus, GHDL, VCS, Questa, Xcelium. Returns structured errors and optional VCD trace path. |
| `synthesize` | Synthesize to gates. Auto-selects from Yosys, Vivado, Quartus, DC Shell. Returns utilization and timing summary. |
| `run_place_route` | Place and route an FPGA netlist. Auto-selects from nextpnr (ice40, ECP5, Nexus, MachXO2). Returns timing summary and utilization. Output bitstream path is passed directly to `program_device`. |
| `program_device` | Program a bitstream to an FPGA. Auto-selects from openFPGALoader. Supports SRAM and SPI flash targets. |
| `lint` | Static analysis. Auto-selects from Verible, Verilator, SpyGlass. Returns structured warnings. |
| `run_formal` | Formal verification and equivalence checking. Auto-selects from SymbiYosys, eqy, JasperGold, VC Formal. Returns pass/fail/error with counterexample traces. |
| `launch_waveform` | Open a VCD/FST/FSDB trace in Surfer, GTKWave, or Verdi (fire-and-forget). |
| `read_waveform` | Read signal values straight out of a VCD trace (pure Python, no viewer). List available signals, then fetch transitions for chosen signals in a time window — lets the model inspect waveforms autonomously. |
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
- `debug_formal_failure` — triage a formal FAIL/UNKNOWN from the counterexample trace to a verified fix
- `cdc_review` — enumerate and classify every clock domain crossing against known-safe patterns

## Architecture

```
silica/
├── silica/
│   ├── server.py              # FastMCP server; registers all tools and prompts
│   ├── cli.py                 # subcommand dispatch (serve / setup / config)
│   ├── tools_registry.py      # canonical list of EDA tools (per-OS support + install)
│   ├── clients_registry.py    # canonical list of all supported MCP clients
│   ├── terminal.py            # OSC 8 hyperlink support
│   ├── config.py              # ~/.silica/config.toml load/save
│   ├── oss_cad_suite.py       # detect an existing OSS CAD Suite; binary resolution
│   ├── setup.py               # interactive setup wizard + config viewer
│   ├── tools/                 # MCP tool definitions
│   │   ├── _config_dispatch.py  # config-aware auto tool selection
│   │   ├── simulation.py      # run_simulation()
│   │   ├── synthesis.py       # synthesize()
│   │   ├── place_route.py     # run_place_route()
│   │   ├── program.py         # program_device()
│   │   ├── lint.py            # lint()
│   │   ├── formal.py          # run_formal()
│   │   ├── waveform.py        # launch_waveform(), read_waveform()
│   │   └── project.py         # read_rtl(), write_rtl(), get_project_structure(), ...
│   └── adapters/              # per-tool CLI wrappers + output parsers
│       ├── _hints.py          # platform-aware install hint strings
│       ├── verilator.py       # open source
│       ├── icarus.py
│       ├── ghdl.py
│       ├── yosys.py
│       ├── nextpnr.py
│       ├── openfpgaloader.py
│       ├── verible.py
│       ├── sby.py
│       ├── eqy.py
│       ├── vcs.py             # commercial (detected if on PATH)
│       ├── questa.py
│       ├── xcelium.py
│       ├── vivado.py
│       ├── quartus.py
│       ├── dc_shell.py
│       ├── jaspergold.py
│       ├── vc_formal.py
│       ├── spyglass.py
│       └── verdi.py
└── examples/
    └── uart/                  # 8N1 UART TX — reference design for end-to-end testing
```

## Toolchain coverage

| Category | Open source | Commercial (detected if on PATH) |
|---|---|---|
| Simulation | Verilator, Icarus Verilog, GHDL | VCS (Synopsys), Questa (Siemens), Xcelium (Cadence) |
| Synthesis | Yosys | Vivado (AMD/Xilinx), Quartus (Intel), DC Shell (Synopsys) |
| Place & Route | nextpnr (ice40, ECP5, Nexus, MachXO2) | — |
| Formal | SymbiYosys, eqy | JasperGold (Cadence), VC Formal (Synopsys) |
| Lint | Verible, svlint | SpyGlass (Synopsys) |
| Waveform | GTKWave, Surfer | Verdi (Synopsys) |
| Program | openFPGALoader | — |

## Development

```bash
git clone https://github.com/simaanc/silica-eda
cd silica-eda
uv sync                  # installs silica-eda editable + dev deps (pytest, ruff)

# Run the test suite and linter
uv run pytest tests/ -q
uv run ruff check silica/ tests/

# Run the server locally (for debugging)
uv run silica serve

# Run the UART end-to-end test
iverilog -g2012 -o /tmp/uart_sim examples/uart/uart_tx_tb.sv examples/uart/uart_tx.sv
vvp /tmp/uart_sim
```

## License

silica is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only). You can use, modify and redistribute it, including commercially. If you distribute a modified version, or run one as a service that others interact with over a network, you must make your changes' source available under the same license.
