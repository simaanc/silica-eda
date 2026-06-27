# Silica

AI-native EDA environment — an MCP server that gives any LLM deep integration with the full EDA toolchain: simulation, synthesis, linting, formal verification, and autonomous debug loops.

## What it does

Silica wraps open source EDA tools (Verilator, Yosys, Verible, Icarus) in a structured MCP interface. You describe what you want to the model; Silica gives it the tool access and reasoning skills to find and fix RTL bugs, synthesize designs, and run verification workflows autonomously.

The core value: **closed autonomous loops**. Run sim → parse failure → reason about RTL → propose fix → re-run — without human copy-paste.

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

**Easiest path — OSS CAD Suite (Linux & Windows).** YosysHQ publishes a single binary bundle that includes Verilator, Icarus, Yosys, SymbiYosys, Surfer, GTKWave, and all the SMT solvers. Download it from the [releases page](https://github.com/YosysHQ/oss-cad-suite-build/releases) and extract it — silica uses the bundled tools directly, with no PATH setup or `environment` sourcing needed. This covers everything except the linters (Verible / svlint), which you install separately. On **macOS**, use Homebrew instead (the OSS CAD Suite macOS builds are unreliable upstream).

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

Otherwise, the wizard prints per-tool install commands for whatever you selected but don't have. By platform:

**macOS**
```bash
brew install verilator yosys icarus-verilog surfer
brew tap chipsalliance/verible && brew install verible
```

**Ubuntu / Debian**
```bash
sudo apt update && sudo apt install verilator yosys iverilog gtkwave
# Verible has no apt package — grab the release binary:
#   https://github.com/chipsalliance/verible/releases
```

**Fedora / RHEL**
```bash
sudo dnf install verilator yosys iverilog gtkwave
```

**Arch**
```bash
sudo pacman -S verilator yosys iverilog gtkwave
```

**Windows**
Install OSS CAD Suite (native, recommended) from its [releases page](https://github.com/YosysHQ/oss-cad-suite-build/releases) for Verilator/Icarus/Yosys/SymbiYosys/Surfer/GTKWave — silica detects it automatically. Add Verible from its [GitHub releases](https://github.com/chipsalliance/verible/releases) (`win64.zip`). WSL2 also works if you prefer a Linux environment — install the Ubuntu packages above inside WSL and point your client at `wsl -e silica serve`.

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

## MCP Tools (v0.1)

| Tool | Description |
|---|---|
| `run_simulation` | Simulate RTL (Verilator / Icarus). Returns structured errors and optional VCD trace path. |
| `synthesize` | Synthesize to gates (Yosys). Returns utilization. |
| `lint` | Static analysis (Verible / Verilator). Returns structured warnings. |
| `run_formal` | Formal verification (SymbiYosys). Returns pass/fail/error status. |
| `launch_waveform` | Open a VCD trace in Surfer or GTKWave (fire-and-forget). |
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
│   │   ├── lint.py            # lint()
│   │   ├── formal.py          # run_formal()
│   │   ├── waveform.py        # launch_waveform()
│   │   └── project.py         # read_rtl(), write_rtl(), get_project_structure(), ...
│   └── adapters/              # per-tool CLI wrappers + output parsers
│       ├── _hints.py          # platform-aware install hint strings
│       ├── verilator.py
│       ├── icarus.py
│       ├── yosys.py
│       ├── verible.py
│       └── sby.py
└── examples/
    └── uart/                  # 8N1 UART TX — reference design for end-to-end testing
```

## Toolchain coverage (v0.1)

| Category | Open source | Commercial (detected if on PATH) |
|---|---|---|
| Simulation | Verilator, Icarus Verilog | VCS (Synopsys), Questa (Siemens), Xcelium (Cadence) |
| Synthesis | Yosys | Vivado (AMD/Xilinx), Quartus (Intel), DC Shell (Synopsys) |
| Formal | SymbiYosys | JasperGold (Cadence), VC Formal (Synopsys) |
| Lint | Verible, svlint | SpyGlass (Synopsys) |
| Waveform | GTKWave, Surfer | Verdi (Synopsys) |

## Development

```bash
git clone https://github.com/simaanc/silica-eda
cd silica-eda
pip install -e ".[dev]"

# Run the server locally (for debugging)
silica serve

# Run the UART end-to-end test
iverilog -g2012 -o /tmp/uart_sim examples/uart/uart_tx_tb.sv examples/uart/uart_tx.sv
vvp /tmp/uart_sim
```

## License

Apache-2.0
