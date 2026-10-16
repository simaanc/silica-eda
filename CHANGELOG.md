# Changelog

All notable changes to silica-eda are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
- `LICENSE` now holds the verbatim Apache License 2.0 text, and the copyright
  notice moved to `NOTICE`. The package metadata declares the license as an
  SPDX expression.

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
