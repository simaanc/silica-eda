# Changelog

All notable changes to silica-eda are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- A `doctor` tool that reports silica's version, whether a newer release is
  on PyPI, the version of every open-source EDA tool silica can find
  (Verilator, Verible, svlint, Icarus, GHDL, SymbiYosys, eqy, Yosys, the
  nextpnr variants, openXC7's nextpnr-xilinx and fpga-as, openFPGALoader,
  Surfer, GTKWave), the optional cocotb and pyserial extras, and which
  commercial tools are on PATH. Each missing or outdated tool comes with a
  fix for this platform. Commercial tools are looked up, never run. Set
  `SILICA_NO_UPDATE_CHECK=1` to skip the PyPI check.
- A `silica-eda` command, the same as `silica`, so `uvx silica-eda` starts
  the MCP server. uvx runs the executable named after the package, and
  `uvx silica-eda` used to fail with "An executable named `silica-eda` is
  not provided".
- `run_place_route` places and routes Xilinx 7-series parts with
  `arch="xilinx"` through openXC7's nextpnr-xilinx, taking an `.xdc`
  constraint file and a part such as `xc7a100tcsg324-1`. When openXC7's
  `fpga-as` and `PRJXRAY_DB_DIR` are available the result is a `.bit` ready
  for `program_device`; otherwise it is the FASM file, with a warning.
- `capture_serial` reads a board's UART for a set time, optionally sending
  text first, and returns the received lines with timestamps, the byte count
  and whether an `expect` regex matched. It opens only the port it is given.
  A missing or inaccessible port comes back as an error with the command
  that fixes it. Needs the new `serial` extra (`pip install
  "silica-eda[serial]"`).
- `synthesize` with Yosys lists the inferred memories under `memories`: name,
  depth, width, ports, how each was mapped (block RAM, distributed RAM,
  logic, or optimized away) and whether it has init data. A read-only memory
  with no init data (firmware loaded only under `` `ifdef SIM``, say) also
  adds a warning, because synthesis otherwise drops it without a trace.

### Fixed
- Tool descriptions that clients read now match what the tools do:
  `get_project_structure` returns `rtl_files`, `constraint_files` and
  `file_count` (not `files` and `top_candidates`); `program_device` takes a
  `.bit` or `.bin`, not nextpnr's `.asc`/`.textcfg`, and "arty" is the 35T
  board; `run_place_route` produces a programmable `.bit` only for Xilinx;
  `run_simulation` notes that tracing needs `$dumpfile`/`$dumpvars` in the
  testbench.
- `run_simulation` with VCS, Questa or Xcelium accepts relative source paths and
  runs the simulation in the DUT's directory, like Icarus and Verilator, so
  relative testbench paths such as `$readmemh("../fw/firmware.hex")` resolve
  the same way with or without tracing. Questa and Xcelium always simulated
  in a temp directory, so these paths never worked there. (Checked with mocked tool
  calls only.)
- `synthesize` with Yosys fills in `file` and `line` for errors and warnings
  when Yosys gives a location, either as a prefix (`top.sv:12: ERROR: ...`)
  or as an `at top.sv:12.5-12.9` clause. They were always `""` and `0`.
  Warnings with a location prefix were not reported at all, and an error
  with one came back as "Yosys synthesis failed"; both are now returned.
- `synthesize` with Yosys says which file it could not open when a
  `$readmemh` path is wrong. Errors that Yosys prefixes with a location
  (`rom.v:4: ERROR: ...`) were not recognized, so the result only said
  "Yosys synthesis failed".
- `lint` with Verible reports its findings again. Current Verible releases
  print a column range (`file.sv:22:20-31:`), which the parser skipped, so
  every warning and syntax error was dropped.
- `lint` with svlint 0.9 reports its findings. svlint now prints colored,
  multi-line `Fail:` blocks even when piped, which the parser did not match.
- `run_simulation` with Verilator no longer refuses to simulate a design that
  has lint warnings. The build used `-Wall` with warnings fatal, so an unused
  testbench signal stopped the run with exit code 1 and an empty `errors`
  list. Warnings are still returned in `warnings`, and a failed build with no
  parsed diagnostic now carries an error entry.
- `synthesize` with Yosys reports real utilization for FPGA targets. LUTs,
  flip-flops, block RAM and DSPs mapped to ice40, ecp5, gowin and xilinx
  primitives were not counted, so those targets always reported zero, and
  the generic target counted every flip-flop about four times.
- `program_device` reports a failed Xilinx load as a failure. openFPGALoader
  exits 0 even when the FPGA never asserts DONE (for example, after a
  bitstream whose header declares a zero length), so the tool returned
  `success: true` for a board that was left unconfigured.
- `run_place_route` lists each clock once, with its routed result.
  nextpnr reports every clock after placement and again after routing, and
  both entries were returned, with the placement estimate first.
- `lint` with Verilator reports errors. Only Verilator's warnings were
  passed through, so a syntax error or a missing module came back as a clean
  result; errors now appear in `warnings` with `severity: "error"`.
- `lint` with Verilator elaborates `file` and `extra_files` together. Each
  file used to be linted on its own, so a top-level module reported every
  submodule as missing and a multi-file design could not be linted.
- `run_simulation` with `trace` (or Verilator `coverage`) no longer breaks
  relative paths in the testbench. Traced runs used to execute in a temporary
  directory, so a `$readmemh("../fw/firmware.hex")` that worked untraced
  failed to open its file. Every run now starts in the DUT's directory, and
  the VCD and `coverage.dat` still end up in the persistent output directory.
- `run_simulation` reports why a simulation failed. Icarus and Verilator print
  `$fatal`, `$error` and runtime errors such as a missing `$readmemh` file on
  stdout, which was not parsed, so `errors` only said "Simulation exited with
  code 1" (and an Icarus `$error`, which exits 0, was not reported at all).
- `synthesize` accepts relative source paths. The synthesis tools run in a
  temporary directory, so `files=["rtl/top.sv"]` failed with "File not
  found" even though `lint` and `run_simulation` took the same paths.
- `run_formal` with sby no longer lists an unproven induction step as a
  failure. An UNKNOWN prove (base case passes, k-induction does not close)
  used to fill `failures` and `traces` as if a bug had been found. Those
  entries now go in `induction_failures` and `induction_traces`, and
  `failures` holds only reachable counterexamples.

## [0.3.1] - 2026-10-16

### Fixed
- The banner image and LICENSE links in the README work on the PyPI project
  page.

## [0.3.0] - 2026-10-16

### Changed
- silica is licensed under the GNU Affero General Public License v3.0
  (AGPL-3.0-only). It replaces all earlier PyPI releases.
- Contributions require a Developer Certificate of Origin sign-off
  (`git commit -s`); see CONTRIBUTING.md.

## [0.2.0] - 2026-10-16

### Changed
- silica now runs on the mcp 2.x Python SDK and requires `mcp>=2.3,<3`.
  Tools, prompts and their schemas are unchanged for clients. Clients that
  speak MCP protocol 2026-07-28 now connect with it; older clients keep
  working on 2025-11-25.
- The server reports silica's own version to clients. Before, it reported
  the mcp SDK's version.

### Fixed
- `read_waveform` on FST traces is safe when several calls run at once: a
  concurrent call can no longer evict the converted VCD another call is
  reading. mcp 2.x runs tool calls on worker threads, so they can overlap.
- On Windows, concurrent first tool calls no longer race to create the OSS
  CAD Suite `.bat` wrappers.

## [0.1.10] - 2026-10-16

### Added
- `cocotb` extra: `pip install "silica-eda[cocotb]"` installs a cocotb that
  `run_cocotb` supports (1.9 or newer).
- Python 3.13 and 3.14 support.
- Security policy, contributing guide, code of conduct, and issue and pull
  request templates.

### Fixed
- `run_formal` equivalence checking (eqy) reported inequivalent sequential
  designs as equivalent. Generated configs now use the `sby` strategy
  instead of `sat`.
- eqy failures are parsed from eqy's real output, so `failures` lists the
  partitions that failed to prove.
- An eqy run that aborts before finishing reports `ERROR` instead of
  `UNKNOWN`.
- `run_cocotb` works with cocotb 2.x, which moved the runner API to
  `cocotb_tools.runner`.
- `run_cocotb` reports an error instead of a silent 0 passed / 0 failed when
  no test results are produced.
- Relative paths given to the file tools are resolved against the project
  root, not the server's working directory. Before this, relative paths were
  rejected whenever `SILICA_PROJECT_ROOT` or `project.root` pointed somewhere
  other than the working directory.
- `search_rtl` and `get_project_structure` are confined to the project root
  like the other file tools.

### Changed
- The copyright notice moved to `NOTICE`, and the package metadata declares
  the license as an SPDX expression.

## [0.1.9] - 2026-07-22

### Added
- Multi-file designs and `.f` filelists for simulation, synthesis and lint.
- `format_rtl`, which formats SystemVerilog/Verilog with
  verible-verilog-format and shows a diff first.
- Coverage collection: `run_simulation(coverage=True)` with Verilator, and
  `read_coverage`.
- `run_cocotb` for Python (cocotb) testbenches.

## [0.1.8] - 2026-07-21

### Fixed
- Each sby run gets its own work directory, so traces from designs with the
  same file name no longer overwrite each other.

### Changed
- FST to VCD conversion is cached across `read_waveform` calls.

## [0.1.7] - 2026-07-21

### Added
- `read_waveform`, which inspects VCD and FST signals without a viewer.
- `project.root` config key and `SILICA_PROJECT_ROOT` for clients that start
  the server outside the project directory.
- `synthesize` returns a JSON netlist for FPGA targets, ready for
  `run_place_route`.
- `debug_formal_failure` and `cdc_review` workflow skills.
- `silica config` shows friendly tool names and the project root.

### Fixed
- `generate_sby` reports an error for duplicate source file names.

## [0.1.6] - 2026-07-02

### Changed
- Code-style cleanup with no functional changes.

## [0.1.5] - 2026-07-02

### Added
- The config's enabled-tool lists are enforced, including when a tool is
  named explicitly.

### Fixed
- `read_rtl`, `write_rtl` and `get_constraints` are confined to the project
  directory.
- Paths with script metacharacters are rejected before they are put into
  generated scripts.
- Every adapter returns a structured error on timeout.
- The auto-generated sby flow copies sources next to the `.sby` file.
- Assorted robustness fixes: config loading, temp-directory leaks, Questa
  `vlib` timeouts, and missing workflow skill files.

## [0.1.4] - 2026-07-02

### Added
- Unit test suite covering every tool and adapter, plus integration tests
  against the real OSS tools.

### Fixed
- Integration failures on Windows with OSS CAD Suite.

## [0.1.3] - 2026-06-27

### Added
- nextpnr place and route, openFPGALoader programming, GHDL VHDL simulation,
  and eqy equivalence checking.

## [0.1.2] - 2026-06-27

### Added
- OS-aware tool registry and OSS CAD Suite detection.
- Commercial tool support (VCS, Questa, Xcelium, Vivado, Quartus, DC Shell,
  JasperGold, VC Formal, SpyGlass, Verdi).

## [0.1.1] - 2026-06-24

### Fixed
- The setup wizard runs CLI client config commands automatically.

## [0.1.0] - 2026-06-24

Initial release: simulation with VCD tracing (Verilator, Icarus), synthesis
(Yosys), lint (Verible, Verilator), formal verification (SymbiYosys),
waveform viewer launch, and the `silica setup` wizard.

[Unreleased]: https://github.com/simaanc/silica-eda/commits/main
[0.3.1]: https://pypi.org/project/silica-eda/0.3.1/
[0.3.0]: https://pypi.org/project/silica-eda/0.3.0/
[0.2.0]: https://pypi.org/project/silica-eda/0.2.0/
[0.1.10]: https://pypi.org/project/silica-eda/0.1.10/
[0.1.9]: https://pypi.org/project/silica-eda/0.1.9/
[0.1.8]: https://pypi.org/project/silica-eda/0.1.8/
[0.1.7]: https://pypi.org/project/silica-eda/0.1.7/
[0.1.6]: https://pypi.org/project/silica-eda/0.1.6/
[0.1.5]: https://pypi.org/project/silica-eda/0.1.5/
[0.1.4]: https://pypi.org/project/silica-eda/0.1.4/
[0.1.3]: https://pypi.org/project/silica-eda/0.1.3/
[0.1.2]: https://pypi.org/project/silica-eda/0.1.2/
[0.1.1]: https://pypi.org/project/silica-eda/0.1.1/
[0.1.0]: https://pypi.org/project/silica-eda/0.1.0/
