# Silica — RTL and FPGA workflow

You have the Silica MCP server: tools that run real EDA tools (Verilator, Icarus, Yosys, SymbiYosys, nextpnr, openFPGALoader, and commercial simulators when installed) and return structured results. Work like a senior RTL engineer: lint and simulate before you synthesize, read the structured errors, fix the RTL, and re-run to confirm.

## First steps in a new environment

1. `doctor` — which EDA tools are installed, their versions, and a concrete fix for anything missing. Run it before promising a flow the machine can't run.
2. `get_project_structure` — find the RTL, testbench and constraint files.

## Workflow order

Go in this order and stop at the first stage that fails:

1. **`lint`** — catches most syntax and width bugs fastest. For Verilator, pass the design's other files in `extra_files` so it can elaborate the whole design.
2. **`run_simulation`** — functional check with a testbench. Add `trace=True` (the testbench must call `$dumpfile`/`$dumpvars`) and inspect with `read_waveform`; `coverage=True` (Verilator) then `read_coverage`.
3. **`run_formal`** — invariants and protocol properties (SymbiYosys), or equivalence (`tool="eqy"`).
4. **`synthesize`** — resources and inferred memories. FPGA targets return a `netlist`.
5. **`run_place_route`** — pass that `netlist`, the constraint file and the part; returns routed timing per clock and the output path.
6. **`program_device`** — load the bitstream into SRAM.
7. **`capture_serial`** — read what the design prints over its UART.

## Tools

| Tool | Use it to |
|---|---|
| `doctor` | Report silica's version, installed EDA tools and versions, and fixes for missing ones. |
| `get_project_structure` | List RTL and constraint files in the project. |
| `read_rtl` / `search_rtl` | Read a file with line numbers / grep the project's RTL. |
| `write_rtl` | Change a file — always `dry_run=True` first (see below). |
| `format_rtl` | Format SystemVerilog with Verible (diff-first, like `write_rtl`). |
| `get_constraints` | Read an .xdc / .sdc / .lpf file. |
| `lint` | Verible, Verilator, svlint (or SpyGlass). Errors come back with `severity: "error"`. |
| `run_simulation` | Verilator, Icarus, GHDL (or VCS, Questa, Xcelium). `$fatal`/`$error` messages come back in `errors`. |
| `run_cocotb` | Run a Python cocotb testbench (needs the `cocotb` extra). |
| `read_waveform` / `launch_waveform` | Read signal transitions from a VCD/FST yourself / open a viewer for the user. |
| `read_coverage` | Summarize Verilator line coverage. |
| `run_formal` | SymbiYosys prove/bmc/cover, eqy equivalence (or JasperGold, VC Formal). |
| `synthesize` | Yosys (or Vivado, Quartus, DC Shell). Returns utilization, `memories`, and a JSON `netlist` for FPGA targets. |
| `run_place_route` | nextpnr: ice40, ecp5, nexus, machxo2, and Xilinx 7-series (`arch="xilinx"`, openXC7). |
| `program_device` | openFPGALoader. |
| `capture_serial` | Read a UART for a set time, optionally send text, match an `expect` regex (needs the `serial` extra). |

Prompts with step-by-step triage scripts: `debug_simulation_failure`, `debug_formal_failure`, `write_testbench`, `generate_assertions`, `close_timing`, `cdc_review`.

## Known pitfalls

- **Paths.** File tools only accept paths inside the project directory. Simulators run in the DUT file's directory, so a testbench's relative `$readmemh("../fw/x.hex")` resolves from there. Yosys resolves `$readmemh` paths relative to the source file. A wrong path is reported with its file and line.
- **Missing firmware.** In `synthesize`, a read-only memory with `has_init: false` usually means its `$readmemh` is under an `` `ifdef `` synthesis skips; Yosys then removes the ROM. Check the `memories` list and warnings before place and route.
- **Formal results.** `status: "FAIL"` with entries in `failures` is a reachable counterexample (see `traces`). `status: "UNKNOWN"` with `induction_failures` is inconclusive, not a bug: the base case passed but k-induction didn't close. Add helper invariants or run `mode="bmc"` with a deeper `depth`; don't "fix" the RTL for it.
- **FPGA flows.** `run_place_route` returns a bitstream `program_device` can load for Xilinx 7-series (`.bit`, openXC7 with `fpga-as`), ice40 (`.bin`, icepack) and ecp5 (`.bit`, ecppack). If the packing tool is missing, `output` is nextpnr's FASM or `.asc`/`.textcfg` and a warning names the missing tool; don't pass that to `program_device`. Programming ice40 and ecp5 boards hasn't been tested on hardware, so report a failure with openFPGALoader's output rather than assuming the bitstream is bad. Timing comes back per clock as the routed `max_freq_mhz`.
- **Programming.** `program_device` loads SRAM by default. Use `spi_flash=True` only when the user asks: it replaces the design the board boots. For Xilinx, success means the FPGA asserted DONE.
- **Serial.** `capture_serial` needs the port named explicitly (e.g. `/dev/ttyUSB1`, or the `-if01-` device for Digilent FTDI boards); silica never scans for ports. If the user can't open it, the result's `fix` is the command to grant access — show it to the user, don't run sudo yourself. The design starts the moment programming finishes, so a boot banner is usually gone before a capture opens: send something the firmware answers, or ask the user to press reset during the capture.
- **What's verified.** Vivado is synthesis only (no implementation or bitstream). The VCS, Questa and Xcelium adapters are tested only with mocked tool calls, not real installs. If one of them misbehaves, say so and suggest the user opens an issue. cocotb needs a Python whose glibc is compatible with the simulator it drives.

## write_rtl() safety protocol

**Never** call `write_rtl(dry_run=False)` before calling `write_rtl(dry_run=True)` and surfacing the diff. The required sequence is:

1. Call `write_rtl(file, new_content, dry_run=True)` — shows the unified diff
2. Present the diff to the user and explain the change
3. Only call `write_rtl(file, new_content, dry_run=False)` after confirmation (or if the user has pre-authorized autonomous fixes)
4. Re-run lint and simulation (or synthesis) to verify the fix

## RTL guidance

- `always_ff` for sequential logic with non-blocking `<=`; `always_comb` with blocking `=` for combinational logic. Never mix the two in one block.
- Every path through an `always_comb` must assign every output, or you get a latch (Yosys reports latches inferred from `always_comb` as errors).
- Two-process FSMs with a `typedef enum` state type and a `default` case.
- Synchronize asynchronous inputs (buttons, UART RX) with two flops before use; release resets synchronously.
- `initial` blocks, `#` delays, `$display`/`$dumpfile`/`$finish` are simulation-only. `initial $readmemh` is the exception: synthesis uses it to load memory contents.
- Size literals and casts explicitly; Verilator's `WIDTH*` warnings usually point at real truncation.

Common Verilator diagnostics: `BLKSEQ` (blocking `=` in `always_ff`), `UNDRIVEN` / `UNUSEDSIGNAL` (unconnected or unread signals), `WIDTHEXPAND` / `WIDTHTRUNC` (operand widths differ), `MODMISSING` (a module's file wasn't passed — add it to `extra_files`), `SYNCASYNCNET` (a signal used as both async reset and data).
