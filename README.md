<!-- mcp-name: io.github.simaanc/silica-eda -->
<div align="center">

<img src="https://raw.githubusercontent.com/simaanc/silica-eda/main/banner.png" alt="Silica" width="414"/>

**AI-native EDA environment** · MCP server for hardware design and verification

[![PyPI](https://img.shields.io/pypi/v/silica-eda?style=flat-square&color=3b82f6&label=pypi)](https://pypi.org/project/silica-eda/)
[![Python](https://img.shields.io/pypi/pyversions/silica-eda?style=flat-square)](https://pypi.org/project/silica-eda/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-22c55e?style=flat-square)](https://github.com/simaanc/silica-eda/blob/main/LICENSE)

</div>

---

## What it does

Silica is an MCP server that gives coding agents structured access to an EDA toolchain. The agent lints, simulates, proves, synthesizes, places and routes, programs a board and reads its UART through MCP tools, and gets parsed results back (errors with file and line, timing per clock, utilization, inferred memories, counterexample traces) instead of raw logs.

That closes the loop without copy-paste: run the simulation, read the failure, fix the RTL, re-run. The server also tells the agent the order to work in and the pitfalls to avoid, and a `doctor` tool reports which EDA tools are installed and how to install the rest.

Silica drives tools you install yourself: open-source tools (mostly from [OSS CAD Suite](docs/eda-tools.md)), and commercial ones (VCS, Questa, Xcelium, Vivado, …) when they're on `PATH`. How well each is tested is listed under [Supported tools](#supported-tools).

## What works today

The full flow has been run end to end on a **Digilent Arty A7-100T** (Xilinx Artix-7) with a PicoRV32 RISC-V SoC whose firmware prints a banner, echoes UART input and drives LEDs from a timer:

1. **RTL and lint**: Verilator, Verible and svlint, with Verilator elaborating the whole multi-file design.
2. **Simulation**: Icarus and Verilator running the real firmware from `$readmemh`, with waveform (`read_waveform`) and line coverage (`read_coverage`).
3. **Formal**: SymbiYosys prove, cover and bounded checks on the UART and FIFO, a deliberately false assertion reported as FAIL with its counterexample, and eqy equivalence.
4. **Synthesis**: Yosys `synth_xilinx`, with utilization and the firmware ROM reported as block RAM with init data.
5. **Place and route**: openXC7's nextpnr-xilinx (100 MHz target, routed at 153 MHz), and the `.bit` assembled with `fpga-as`.
6. **Programming**: `program_device` (openFPGALoader) into SRAM, with the FPGA's DONE status checked.
7. **Serial check**: `capture_serial` confirming the banner and the echo over the board's UART.

These runs were manual, on one machine (OSS CAD Suite 2026-10-14, openXC7 toolchain-nix 1.0.0, Verible v0.0-4296, svlint 0.9.5). CI covers the open-source tools in a weekly integration job; see [Supported tools](#supported-tools).

## Known limitations

- **Vivado** is synthesis only: there's no implementation or bitstream step.
- **VCS, Questa and Xcelium** adapters are tested only with mocked tool calls, never against a real install; the same goes for Quartus, DC Shell, JasperGold, VC Formal, SpyGlass and Verdi. If one misbehaves, please [open an issue](https://github.com/simaanc/silica-eda/issues) with the tool version and output.
- **iCE40 and ECP5** bitstreams are packed with icepack/ecppack and checked against the real tools, but `program_device` has only been tested on these boards with mocked openFPGALoader calls: no iCE40 or ECP5 board has been available. `get_project_structure` doesn't list iCE40 `.pcf` files.
- **cocotb** needs a Python whose glibc is compatible with the simulator it loads into. With OSS CAD Suite's simulators and a newer system Python (glibc newer than the suite's), `run_cocotb` fails at import.
- **Formal**: an `UNKNOWN` prove with `induction_failures` is inconclusive (k-induction didn't close), not a bug. Deep bounded checks can be slow; 120 steps on the example UART took 16 minutes.
- **Serial**: `capture_serial` needs the port named explicitly and read/write access to it. A boot banner is usually missed by a capture started after programming.
- **Windows**: the serial existence and permission pre-checks are POSIX-only, and the pty-based serial tests skip there.

## Quick start

1. **Add silica to your agent.** Follow [Install in your agent](#install-in-your-agent): each client launches `uvx silica-eda@latest`. (With pip instead: `pip install silica-eda`, then `silica setup` writes the config for Claude Desktop, Claude Code, Cursor, Zed, Windsurf, OpenCode or Gemini CLI.)
2. **Install the EDA tools** you need: [OSS CAD Suite](docs/eda-tools.md#oss-cad-suite-most-open-source-tools) for most open-source tools, [Verible and svlint](docs/eda-tools.md#linters) for linting, [openXC7](docs/eda-tools.md#xilinx-7-series-place-and-route-openxc7) for Xilinx place and route. Then ask the agent to run `doctor`.
3. **Try the UART example** in [`examples/uart/`](examples/uart/):

   > Run the UART TX simulation in examples/uart/ and tell me if it passes.

   Then break it and let the agent find the bug:

   > In examples/uart/uart_tx.sv, change the DATA state's shift to `shift_reg <= {shift_reg[6:0], 1'b0};`. Run the simulation, find the bug and fix it.

   The testbench then prints `[FAIL]` lines such as `bit[2] is 0, expected 1`, and the agent should trace them to the shift direction.

## Install in your agent

Every client below starts the server with `uvx silica-eda@latest`: [uv](https://docs.astral.sh/uv/getting-started/installation/) downloads silica into a cached environment on first use and picks up new releases when the client next starts the server. Install uv first. `uvx silica-eda` needs a silica-eda release newer than 0.3.1; on 0.3.1 use `uvx --from silica-eda@latest silica` instead.

silica drives EDA tools you install separately (Verilator, Yosys, SymbiYosys, nextpnr, …); see [Installing the EDA tools](docs/eda-tools.md). Once connected, ask the agent to run the `doctor` tool: it lists what's installed and how to install what's missing.

<details>
<summary><b>Claude Code</b> (plugin, with a workflow skill)</summary>

In Claude Code:

```text
/plugin marketplace add simaanc/silica-eda
/plugin install silica-eda@silica-eda
```

On Claude Code 2.1.275 or later this also works in one step: `/plugin install silica-eda --marketplace simaanc/silica-eda`.

Updates: the plugin's server always runs `uvx silica-eda@latest`. To also receive plugin updates (new skills, config changes) automatically, turn on auto-update for the marketplace, which is off by default: `/plugin` → **Marketplaces** → **silica-eda** → **Enable auto-update**. Admins can set `"autoUpdate": true` on the marketplace's `extraKnownMarketplaces` entry in managed settings. Without auto-update, run `/plugin marketplace update silica-eda`.

Without the plugin, add just the server:

```bash
claude mcp add --transport stdio --scope user silica -- uvx silica-eda@latest
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

Open **Settings → Developer → Edit Config** and add the server to `claude_desktop_config.json`, then quit and restart Claude Desktop:

```json
{
  "mcpServers": {
    "silica": {
      "command": "uvx",
      "args": ["silica-eda@latest"]
    }
  }
}
```

If the server doesn't start, Claude Desktop may not see your shell's `PATH`: put the full path from `which uvx` in `command`.

</details>

<details>
<summary><b>Codex CLI</b></summary>

```bash
codex mcp add silica -- uvx silica-eda@latest
```

or in `~/.codex/config.toml`:

```toml
[mcp_servers.silica]
command = "uvx"
args = ["silica-eda@latest"]
# The first launch downloads silica; Codex's default start timeout is 10 s.
startup_timeout_sec = 60
```

</details>

<details>
<summary><b>Cursor</b></summary>

Add to `~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project):

```json
{
  "mcpServers": {
    "silica": {
      "type": "stdio",
      "command": "uvx",
      "args": ["silica-eda@latest"]
    }
  }
}
```

One-click install: open this link in your browser (GitHub doesn't make `cursor://` links clickable):

```text
cursor://anysphere.cursor-deeplink/mcp/install?name=silica&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJzaWxpY2EtZWRhQGxhdGVzdCJdfQ==
```

</details>

<details>
<summary><b>VS Code (GitHub Copilot)</b></summary>

```bash
code --add-mcp '{"name":"silica","type":"stdio","command":"uvx","args":["silica-eda@latest"]}'
```

or in `.vscode/mcp.json` (workspace) or your user-profile `mcp.json`:

```json
{
  "servers": {
    "silica": {
      "type": "stdio",
      "command": "uvx",
      "args": ["silica-eda@latest"]
    }
  }
}
```

</details>

<details>
<summary><b>Gemini CLI</b></summary>

```bash
gemini mcp add -s user silica uvx silica-eda@latest
```

or in `~/.gemini/settings.json` (user) or `.gemini/settings.json` (project):

```json
{
  "mcpServers": {
    "silica": {
      "command": "uvx",
      "args": ["silica-eda@latest"]
    }
  }
}
```

</details>

**Optional extras.** `capture_serial` needs pyserial and `run_cocotb` needs cocotb. With uvx, add them to the arguments: `"args": ["--with", "pyserial", "silica-eda@latest"]` (or `--with cocotb`). With pip, install `silica-eda[serial]` or `silica-eda[cocotb]`.

**Pin a version or roll back.** Replace `silica-eda@latest` with an exact version, `silica-eda@<version>` (for example `uvx silica-eda@0.4.0` once that release exists), and the client keeps running that release until you change it. To roll back after a bad release, pin the previous version the same way. The Claude Code plugin always runs `@latest`; to pin there, add the server with `claude mcp add` and a pinned version instead of installing the plugin. Releases are listed on [PyPI](https://pypi.org/project/silica-eda/#history) and in the [changelog](https://github.com/simaanc/silica-eda/blob/main/CHANGELOG.md).

## MCP tools

| Tool | Description |
|---|---|
| `doctor` | Report silica's version, whether a newer release exists, which EDA tools are installed (with versions) and how to install missing ones. |
| `lint` | Verible, Verilator, svlint or SpyGlass. Verilator elaborates `file` and `extra_files` together. Errors and warnings come back with file, line and rule. |
| `format_rtl` | Format SystemVerilog with verible-verilog-format. Diff-first (`dry_run`), refuses files with syntax errors. |
| `run_simulation` | Verilator, Icarus, GHDL, VCS, Questa or Xcelium. Runs in the DUT's directory; returns errors including `$fatal`/`$error` messages, an optional VCD (`trace`, testbench calls `$dumpfile`/`$dumpvars`) and Verilator coverage. |
| `run_cocotb` | Run a cocotb (Python) testbench; per-test pass/fail. Needs the `cocotb` extra. |
| `read_waveform` | Read signal transitions from a VCD/FST trace in a time window, without a viewer. |
| `launch_waveform` | Open a trace in Surfer, GTKWave or Verdi for the user. |
| `read_coverage` | Summarize a Verilator `coverage.dat` per file with uncovered lines. |
| `run_formal` | SymbiYosys prove/bmc/cover, eqy equivalence, JasperGold, VC Formal. `failures` are reachable counterexamples (with traces); an `UNKNOWN` prove lists `induction_failures` instead. |
| `synthesize` | Yosys, Vivado, Quartus or DC Shell. Utilization, errors with file and line, a JSON netlist for FPGA targets, and (Yosys) every inferred memory with its mapping and whether it has init data. |
| `run_place_route` | nextpnr for ice40, ECP5, Nexus, MachXO2 and Xilinx 7-series (`arch="xilinx"`, openXC7). Returns a loadable bitstream for Xilinx (`.bit` via `fpga-as`), iCE40 (`.bin` via `icepack`) and ECP5 (`.bit` via `ecppack`). Routed timing per clock and utilization. |
| `program_device` | openFPGALoader. SRAM by default, SPI flash on request; a Xilinx load counts as success only when the FPGA asserts DONE. Takes `.bit`/`.bin`. |
| `capture_serial` | Read a UART for a set time, optionally send text, match an `expect` regex. Opens only the port you name. Needs the `serial` extra. |
| `get_project_structure` | List the project's RTL and constraint files. |
| `read_rtl` / `search_rtl` | Read a file with line numbers / grep the project's RTL. |
| `write_rtl` | Change a file, diff-first (`dry_run=True` by default). |
| `get_constraints` | Read a constraint file (.xdc, .sdc, .lpf). |

Prompts with step-by-step triage scripts: `debug_simulation_failure`, `debug_formal_failure`, `write_testbench`, `generate_assertions`, `close_timing`, `cdc_review`.

## Supported tools

| Tool | Used by | Verification |
|---|---|---|
| Verilator | `lint`, `run_simulation`, `read_coverage` | Real tool in CI; used in the Arty A7 flow |
| Icarus Verilog | `run_simulation`, `run_cocotb` | Real tool in CI; used in the Arty A7 flow |
| GHDL | `run_simulation` (VHDL) | Real tool in CI |
| cocotb | `run_cocotb` | Real tool in CI |
| Verible, svlint | `lint`, `format_rtl` | Real tools, tested locally (not in CI) |
| Yosys | `synthesize` | Real tool in CI (generic, ice40, xilinx); used in the Arty A7 flow |
| SymbiYosys, eqy | `run_formal` | Real tools in CI |
| nextpnr-ice40 + icepack | `run_place_route` (`arch="ice40"`) | Real tools in CI (place and route, packing); programming mocked only |
| nextpnr-ecp5 + ecppack | `run_place_route` (`arch="ecp5"`) | Real tools in CI (place and route, packing); programming mocked only |
| nextpnr-nexus, -machxo2 | `run_place_route` | Mocked only |
| openXC7 nextpnr-xilinx + fpga-as | `run_place_route` (`arch="xilinx"`) | Tested on hardware (Arty A7-100T) |
| openFPGALoader | `program_device` | Tested on hardware (Arty A7-100T); iCE40 and ECP5 mocked only |
| pyserial | `capture_serial` | Tested on hardware; pty-based tests in CI |
| Surfer, GTKWave, Verdi | `launch_waveform` | Untested (fire-and-forget launch) |
| VCS, Questa, Xcelium | `run_simulation` | Mocked only |
| Vivado | `synthesize` | Mocked only; synthesis only |
| Quartus, DC Shell | `synthesize` | Mocked only |
| JasperGold, VC Formal | `run_formal` | Mocked only |
| SpyGlass | `lint` | Mocked only |

"Real tool in CI" means the weekly integration workflow runs it from OSS CAD Suite. "Tested on hardware" means the manual Arty A7-100T run described under [What works today](#what-works-today). "Mocked only" means unit tests with captured or representative output, never a real install.

## Checking a design on hardware

`program_device` and `capture_serial` close the loop on a real board: program it, then read what the design prints. `capture_serial` needs pyserial, from the `serial` extra:

```bash
pip install "silica-eda[serial]"
```

A typical check after `run_place_route` has produced a bitstream, here checking that the firmware on an Arty A7-100T echoes what it receives:

```text
program_device(bitstream="build/soc.bit", board="arty_a7_100t")
  -> {"success": true, ...}

capture_serial(port="/dev/serial/by-id/usb-Digilent_Digilent_USB_Device_<serial>-if01-port0",
               baud=115200, duration=6, send="hello silica\r", send_delay=0.5,
               expect="hello silica")
  -> {"matched": true, "match": "hello silica", "elapsed_s": 0.53,
      "lines": [{"t": 0.526, "text": "hello silica"}], ...}
```

Name the port explicitly; silica never scans for serial devices. On boards with an FTDI JTAG+UART bridge (Digilent Arty, Basys, Nexys) the UART is the second interface, `if01`. The design starts running as soon as programming finishes, so a banner printed at boot is usually gone before a capture opened afterwards: send something the firmware answers (as above), or press the board's reset button during the capture. If the port is missing or your user can't open it, the result carries an `error` and a `fix` such as:

```text
sudo setfacl -m u:you:rw /dev/ttyUSB1   (temporary: lasts until the device is unplugged);
permanent: sudo usermod -aG uucp you, then log out and back in
```

## Xilinx 7-series flow

With [openXC7 set up](docs/eda-tools.md#xilinx-7-series-place-and-route-openxc7), an Artix-7 design goes from RTL to a programmed board in three calls:

```text
synthesize(top_module="soc_top", files=["rtl/soc_top.sv", ...], target="xilinx", tool="yosys")
  -> {"netlist": "/tmp/silica_synth_.../netlist.json", "memories": [...], ...}

run_place_route(netlist="<netlist>", arch="xilinx", device="xc7a100tcsg324-1",
                constraint="arty.xdc", freq=100, output="build/soc.bit")
  -> {"output": "build/soc.bit", "timing_summary": {"clocks": [{"max_freq_mhz": 153.4, "pass": true}]}, ...}

program_device(bitstream="build/soc.bit", board="arty_a7_100t")
  -> {"success": true, ...}
```

`device` is the full part with speed grade. For the Arty A7-100T the openFPGALoader board is `arty_a7_100t` (`arty` is the 35T).

## Configuration

### Controlling tool selection

By default every detected tool is available and `auto` picks the best one (open-source first). To control this per category, edit `~/.silica/config.toml`:

```toml
[tools.simulation]
priority = ["verilator", "iverilog"]   # ordering for auto-selection
enabled  = ["verilator", "iverilog"]   # allowlist — everything else is blocked
```

`priority` reorders what `auto` tries. `enabled` is an enforced allowlist: tools not on it can't be used **even when the model asks for one explicitly** — the request is rejected with an error naming the tool and what's enabled, so the model can retry with an allowed one. Useful when a machine has commercial tools installed that shouldn't be run (license pools, air-gapped flows). Leave `enabled` empty or unset for no restriction.

Categories: `simulation`, `synthesis`, `place_route`, `formal`, `lint`, `format`, `waveform`, `program`.

### Guardrails

Built for pointing an autonomous agent at a real repo:

- **File access is confined to the project directory** — `read_rtl`, `write_rtl`, `format_rtl`, `get_constraints`, `search_rtl` and `get_project_structure` reject absolute or `..` paths that escape the project root (`SILICA_PROJECT_ROOT`, the `project.root` config key, or the directory the server was started in). Relative paths are resolved against that root.
- **Writes are diff-first** — `write_rtl` defaults to a dry run that returns a unified diff; nothing touches disk until explicitly confirmed.
- **A hung tool never kills the server** — every tool call has a timeout and returns a structured error instead of crashing the session.

### CLI

| Command | Description |
|---|---|
| `silica serve` | Start the MCP server (stdio). Default when no subcommand is given. `silica-eda` is the same command. |
| `silica setup` | Interactive wizard that writes MCP client configs for a pip install. |
| `silica config` | Show the configuration and which tools are detected. |

## Versioning and compatibility

silica follows [Semantic Versioning](https://semver.org/), applied to what MCP clients and agents depend on: tool names, their parameters, and the fields in their results. The same rules hold for 0.x releases.

- **Within a major version** no tool is renamed or removed, no parameter is removed or made required, and no result field is removed or renamed. Minor releases may add tools, optional parameters and result fields.
- **Deprecations** are announced in [CHANGELOG.md](https://github.com/simaanc/silica-eda/blob/main/CHANGELOG.md) and in the affected tool's description at least one minor release before the change ships in the next major version.
- **Every user-visible change** is listed in the changelog when it merges, under "Unreleased", and moves under the version heading at release.

## Development

```bash
git clone https://github.com/simaanc/silica-eda
cd silica-eda
uv sync                                       # editable install + dev deps
uv run ruff check silica/ tests/ scripts/
uv run pytest tests/ -q                       # integration tests skip tools that aren't installed
uv run silica serve                           # run the server from the checkout
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions, [docs/architecture.md](docs/architecture.md) for the code layout, and [RELEASING.md](RELEASING.md) for releases.

## License

silica is licensed under the [GNU Affero General Public License v3.0](https://github.com/simaanc/silica-eda/blob/main/LICENSE) (AGPL-3.0-only). You can use, modify and redistribute it, including commercially. If you distribute a modified version, or run one as a service that others interact with over a network, you must make your changes' source available under the same license.
