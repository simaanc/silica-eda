# Silica — Agent Handoff Document

**Project:** `/Users/simaanc/Developer/silica`  
**Stack:** Python 3.14, uv, FastMCP, tomli-w  
**Package name:** `silica-eda` (PyPI), CLI command: `silica`  
**Last commit:** `b8ad45c` — sby formal verification adapter

---

## What this project is

Silica is an MCP server for EDA (hardware design) toolchains. It wraps open source and commercial EDA tools (simulators, synthesizers, linters, formal verification) in a structured MCP interface so LLMs can run RTL workflows autonomously.

The server exposes MCP tools (`run_simulation`, `synthesize`, `lint`, `run_formal`, `read_rtl`, `write_rtl`, etc.) and MCP prompts (workflow reasoning scripts). It ships with `silica setup` (interactive first-run wizard) and `silica config` (status viewer).

---

## Current file structure

```
silica/
├── silica/
│   ├── server.py               # FastMCP server; registers all tools and prompts
│   ├── cli.py                  # Entry point: dispatches serve / setup / config
│   ├── tools_registry.py       # Canonical list of all 18 supported EDA tools
│   ├── clients_registry.py     # Canonical list of 7 MCP clients
│   ├── terminal.py             # OSC 8 hyperlink support
│   ├── config.py               # load/save ~/.silica/config.toml
│   ├── setup.py                # Interactive wizard + print_config()
│   ├── tools/
│   │   ├── _config_dispatch.py # Config-aware auto tool selection (KEY FILE)
│   │   ├── simulation.py       # run_simulation MCP tool
│   │   ├── synthesis.py        # synthesize MCP tool
│   │   ├── lint.py             # lint MCP tool
│   │   ├── formal.py           # run_formal MCP tool
│   │   └── project.py          # read_rtl, write_rtl, get_project_structure, search_rtl, get_constraints
│   └── adapters/
│       ├── _hints.py           # Platform-aware install hint strings
│       ├── verilator.py        # Verilator compile+sim and lint-only
│       ├── icarus.py           # Icarus Verilog (iverilog/vvp)
│       ├── yosys.py            # Yosys synthesis
│       ├── verible.py          # Verible lint (verible-verilog-lint)
│       └── sby.py              # SymbiYosys formal verification
├── examples/
│   └── uart/
│       ├── uart_tx.sv          # 8N1 UART transmitter (clean, tested)
│       └── uart_tx_tb.sv       # Testbench (clean, passes Verilator)
└── pyproject.toml              # dependencies: mcp>=1.9, tomli-w>=1.0
```

---

## What works right now

- `silica serve` — starts MCP server over stdio
- `silica setup` — interactive wizard; detects installed tools and clients, writes `~/.silica/config.toml`, injects MCP client configs
- `silica config` — reads live tool status, shows install hints for missing tools
- MCP tools: `run_simulation`, `synthesize`, `lint`, `run_formal`, `read_rtl`, `write_rtl`, `get_project_structure`, `search_rtl`, `get_constraints`
- Config-aware dispatch: all auto modes read `~/.silica/config.toml` priority order
- UART example: compiles and passes all 5 simulation test cases cleanly

---

## What's next (in priority order)

### 1. Waveform trace + launch flow

This is the immediate next task. Two parts:

**Part A: `--trace` on `run_simulation`**

Add a `trace: bool = False` parameter to `run_simulation`. When True:
- Verilator: add `--trace` to the compile command and `--trace-fst` or `--trace` flags; output goes to `<tmpdir>/trace.vcd` or `trace.fst`
- Icarus: add `-dumpfile trace.vcd` or use `$dumpfile`/`$dumpvars` (already in the testbench at line 124–125 of `uart_tx_tb.sv`)
- Return the trace file path in the result dict as `trace_vcd`

**Part B: `launch_waveform` MCP tool**

New file: `silica/tools/waveform.py`. New adapter files if needed.

The tool takes a VCD/FST path and opens it in the configured waveform viewer:
```python
def launch_waveform(trace_file: str, viewer: str = "auto") -> dict:
```
- `auto` reads `~/.silica/config.toml` `tools.waveform.priority` via `pick("waveform")`
- For `surfer`: `subprocess.Popen(["surfer", trace_file])` — fire and forget, don't wait
- For `gtkwave`: same pattern
- Return `{"viewer": "surfer", "launched": True, "trace": "/path/to/trace.vcd"}`
- This is a fire-and-forget GUI launch — do NOT use `subprocess.run` (blocks), use `subprocess.Popen`

Register `waveform.register(mcp)` in `server.py`.

The full flow the model can then run:
1. `run_simulation(..., trace=True)` → get `trace_vcd` path
2. `launch_waveform(trace_vcd)` → opens surfer/gtkwave for the user

### 2. Publish to PyPI

`pip install silica-eda` is in the README but the package isn't published. Steps:
- `uv build`
- `uv publish` (needs PyPI token)
- The package name is `silica-eda` (set in `pyproject.toml`)

### 3. More formal verification

The `sby` adapter is complete but there's no example `.sby` file in `examples/`. Add `examples/uart/uart_tx.sby` with a formal proof of the UART protocol properties.

---

## Hard-won lessons — read this before touching anything

### Package manager / tooling
- **Use `uv`**, not pip. The venv has no `pip` binary. Commands: `uv add <pkg>`, `uv sync`, `uv run`.
- Python version is **3.14.1** (via uv). `tomllib` is stdlib (3.11+), no need to install it.

### EDA tool gotchas

**verilator:**
- The binary is `verilator`. Detection works fine.
- `-Wall` promotes warnings to errors. The UART DUT had `WIDTHEXPAND` warnings because `baud_cnt` is `logic [15:0]` but `CLKS_PER_BIT - 1` is 32-bit. Fixed with `16'(CLKS_PER_BIT - 1)` cast in `uart_tx.sv`.
- Testbench had `for (automatic int b = 0; ...)` — Verilator rejects `automatic` in a for-loop variable declaration inside an `automatic` task. Remove `automatic` from the loop; it's redundant there anyway.

**verible:**
- The binary is **`verible-verilog-lint`**, NOT `verible`. There is no `verible` binary. The registry key and `_config_dispatch.py` both use `verible-verilog-lint`.
- `brew install verible` **does not work** — no Homebrew formula. Install via tap: `brew tap chipsalliance/verible && brew install verible`.

**sby (SymbiYosys):**
- The binary name is `sby`, the brew package is also `sby`. The old name `symbiyosys` is wrong for both.
- Default engine `smtbmc` requires a solver. On macOS only `z3` is typically available (`brew install z3`). `yices-smt2`, `bitwuzla`, `boolector` are usually absent. Always detect and specify the solver explicitly: `smtbmc z3`.
- **Critical**: sby resolves `[files]` paths relative to **CWD**, not the `.sby` file location. Always pass `cwd=sby_path.parent` to `subprocess.run`. Without this, sby will look for files in the Python process's CWD (the project root) instead of the `.sby` file's directory and silently fail.
- **Critical**: do NOT pre-create the workdir with `tempfile.mkdtemp()` before passing it to `sby -d <workdir>`. sby needs to create the directory itself. If the directory already exists (even empty), sby's internal setup raises an uncaught Python exception and outputs nothing to stdout/stderr — the subprocess returns rc=1 with empty output and you get UNKNOWN status with no diagnostics. Use `Path(tempfile.gettempdir()) / "silica_sby_<stem>"` as the path without creating it.
- Use `-f` flag to force-remove the workdir on rerun.
- Keep the workdir around (don't use `-t`) so counterexample trace VCDs persist for the waveform viewer.

**gtkwave:**
- `brew install gtkwave` installs it as a **cask** (`brew install --cask gtkwave`), not a formula.
- It is **deprecated/discontinued upstream** (disabled 2025-10-29 in Homebrew). It still installs and works, but warn users.
- Prefer `surfer` as the primary waveform viewer.

**surfer:**
- `cargo install surfer` (crates.io) is **broken** — installs a binary called `test_main`, not `surfer`. Do not use it.
- `brew install surfer` works correctly (Homebrew formula, v0.7.0).
- On Linux, the apt/dnf packages are behind (0.2–0.4). Point users to GitLab releases for Linux.

### Setup wizard (`silica/setup.py`)

- The `multi_select()` widget uses raw terminal mode (`tty.setraw`). It does NOT work when stdin is not a tty (e.g. piped input, CI). Guard with `sys.stdin.isatty()` at the top of `main()`.
- The install hints combiner groups commands by prefix (`brew install X Y Z`) but must special-case `&&`-chained commands (like the verible tap) as solo lines — they can't be merged.
- `_pkg_manager()` returns `"brew"` on macOS. The install dict keys in `tools_registry.py` use `"brew"`, `"apt"`, `"dnf"`, `"pacman"`, `"cargo"`, `"pip"`, `"darwin"`, `"linux"`. Platform keys (`"darwin"`) are a fallback when no package manager key matches.

### MCP client config injection

- **Claude Desktop** config file: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Claude Code**: does NOT use a config file — it's `claude mcp add silica <binary> serve` run in the terminal.
- **Cursor**: `~/.cursor/mcp.json`
- All file-based clients use `"mcpServers"` as the key except Zed (`"context_servers"`) and OpenCode (`"mcp"`).

### `read_rtl` tool

- `Path(file).resolve()` resolves relative to the MCP server's CWD, which when launched by Claude Desktop is NOT the user's project directory — it's typically the home directory or the app's working dir. Always tell the model to use absolute paths. The error message now includes the resolved path to help debug.

### Config round-trip

- `tomllib` (stdlib) reads TOML. `tomli-w` writes TOML. Both in use in `silica/config.py`.
- The config lives at `~/.silica/config.toml`. All keys are strings matching registry names exactly.
- The `_config_dispatch.py` maps registry names to actual binary names (e.g. `"verible-verilog-lint"` → `"verible-verilog-lint"`, `"questa"` → `"vsim"`, `"quartus"` → `"quartus_sh"`).

---

## Testing

There are no pytest tests yet. Manual test protocol:

```bash
# 1. Verify all tools detect correctly
.venv/bin/silica config

# 2. Run the UART simulation end-to-end
.venv/bin/python -c "
from silica.adapters import verilator
r = verilator.run('examples/uart/uart_tx.sv', 'examples/uart/uart_tx_tb.sv', top='uart_tx_tb')
print('exit:', r['exit_code'], '| errors:', r['errors'])
"

# 3. Run formal (needs z3)
.venv/bin/python -c "
from silica.adapters.sby import run, generate_sby
import tempfile
from pathlib import Path
content = generate_sby(['examples/uart/uart_tx.sv'], 'uart_tx')
p = Path(tempfile.mkdtemp()) / 'test.sby'
p.write_text(content)
r = run(str(p))
print('status:', r['status'])
"

# 4. Full MCP test prompt to give Claude:
# 'Using the silica tools, do the following in order:
#  1. get_project_structure on <absolute_path>/examples/uart
#  2. read_rtl on <absolute_path>/examples/uart/uart_tx.sv
#  3. lint on <absolute_path>/examples/uart/uart_tx.sv
#  4. run_simulation with uart_tx.sv and uart_tx_tb.sv
#  5. synthesize with top=uart_tx, files=[uart_tx.sv]
#  6. search_rtl for "always_ff" in examples/uart
# Tell me the exit code and errors from each step.'
```

---

## Known issues / warts

1. **`run_formal` with auto-generated .sby**: uses absolute paths in `[files]` (correct), but the workdir naming is `silica_sby_<stem>` in `/tmp` — if two different .sby files share the same stem name, they'll clobber each other's workdir. Low priority.

2. **`silica setup` multi_select rendering**: if the terminal is very narrow, the hint text wraps awkwardly. No line-length guard.

3. **`_hints.py` vs `tools_registry.py`**: there are now two places with install hints — the old `silica/adapters/_hints.py` (used only by the adapters for error messages when a tool isn't found) and the new `tools_registry.py` (used by the setup wizard). They're partially duplicated. Not a bug, but could be consolidated.

4. **`silica config` binary names**: the display shows the registry key name (e.g. `verible-verilog-lint`) rather than a friendlier display name. Could add a `"display_name"` field to `tools_registry.py`.

5. **No pytest suite**: all testing is manual. The UART example is the de facto integration test.
