# Installing the EDA tools

silica drives EDA tools that you install yourself; it doesn't download or
bundle them. After installing, ask your agent to run the `doctor` tool. It
lists every tool silica can use, the version it found, and the install command
for anything missing.

## OSS CAD Suite (most open-source tools)

YosysHQ's [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases)
is one binary bundle with Verilator, Icarus Verilog, Yosys, SymbiYosys, GHDL,
nextpnr (ice40, ECP5, Nexus, MachXO2), eqy, openFPGALoader, Surfer, GTKWave
and the SMT solvers. Download the release for your platform and extract it.
silica uses the bundled tools directly, with no `PATH` changes or sourcing of
the suite's `environment` script.

silica does **not** download the suite for you: it bundles many tools under
their own licenses, so installing it is your call. silica only detects an
existing install, in this order:

1. The `oss_cad_suite.path` key in `~/.silica/config.toml`:

   ```toml
   [oss_cad_suite]
   path = "/your/path/to/oss-cad-suite"
   ```

2. The `SILICA_OSS_CAD_SUITE` environment variable (also `OSS_CAD_SUITE` or
   `OSS_CAD_SUITE_ROOT`).
3. Common locations: `~/oss-cad-suite`, `~/.silica/oss-cad-suite`,
   `/opt/oss-cad-suite`, `/usr/local/oss-cad-suite` (Linux/macOS), or
   `C:\oss-cad-suite` (Windows).

Point the path at the `oss-cad-suite` folder itself, the one containing `bin/`.
`silica config` (or the `doctor` tool) shows whether it was found. Tools on
your `PATH` take precedence over the suite's.

## Linters

The suite doesn't include the SystemVerilog linters. Install them separately:

- **Verible** (`verible-verilog-lint`, `verible-verilog-format`): release
  binaries from [github.com/chipsalliance/verible/releases](https://github.com/chipsalliance/verible/releases).
- **svlint**: release binaries from
  [github.com/dalance/svlint/releases](https://github.com/dalance/svlint/releases).

## Xilinx 7-series place and route (openXC7)

`run_place_route` with `arch="xilinx"` uses the [openXC7](https://github.com/openXC7)
toolchain, which isn't in OSS CAD Suite. Install it with
[toolchain-nix](https://github.com/openXC7/toolchain-nix) (Nix, or its
container), then make these available to the silica server:

- `nextpnr-xilinx` and `fpga-as` on `PATH`.
- A chip database for your part: `<part without speed grade>.bin` (for
  example `xc7a100tcsg324.bin`) in a directory named by
  `NEXTPNR_XILINX_CHIPDB_DIR` or by the family variable, such as
  `ARTIX7_CHIPDB`. Alternatively, pass the `.bin` path itself as `device`
  (the result is then FASM, not a bitstream).
- `PRJXRAY_DB_DIR` pointing at the prjxray-db root, so `fpga-as` can assemble
  the `.bit`.

Without `fpga-as` or `PRJXRAY_DB_DIR`, `run_place_route` returns the FASM file
and a warning that says what's missing.

## Commercial tools

VCS, Questa, Xcelium, Vivado, Quartus, DC Shell, JasperGold, VC Formal,
SpyGlass and Verdi are used when their binaries are on `PATH`; no other
configuration is needed. `doctor` lists which ones it found. It never runs
them, so it doesn't check out a license.
