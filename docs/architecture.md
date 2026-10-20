# Architecture

silica is an MCP server (`silica/server.py`) that registers one MCP tool per
task. Each tool picks an EDA tool (by config priority, or the one requested)
and calls an adapter that runs it and parses its output into a structured
result.

```
silica/
├── server.py               # MCP server: instructions, prompts, tool registration
├── cli.py                  # silica / silica-eda: serve (default), setup, config
├── doctor.py               # toolchain report behind the doctor tool
├── detect.py               # binary lookup: PATH, then OSS CAD Suite
├── oss_cad_suite.py        # finding an OSS CAD Suite install; its environment
├── config.py               # ~/.silica/config.toml
├── setup.py                # `silica setup` wizard and `silica config`
├── tools_registry.py       # every EDA tool silica knows: category, install info
├── clients_registry.py     # MCP clients the setup wizard can configure
├── vcd.py                  # VCD/FST reading for read_waveform
├── terminal.py             # terminal hyperlinks
├── skills/
│   ├── base/rtl_assistant.md   # sent to clients as the server's instructions
│   └── workflows/*.md          # MCP prompts (debug_simulation_failure, ...)
├── tools/                  # one module per MCP tool
│   ├── simulation.py       # run_simulation
│   ├── cocotb.py           # run_cocotb
│   ├── coverage.py         # read_coverage
│   ├── lint.py             # lint
│   ├── format.py           # format_rtl
│   ├── formal.py           # run_formal
│   ├── synthesis.py        # synthesize
│   ├── place_route.py      # run_place_route
│   ├── program.py          # program_device
│   ├── serial_capture.py   # capture_serial
│   ├── waveform.py         # launch_waveform, read_waveform
│   ├── project.py          # read_rtl, write_rtl, search_rtl, get_project_structure, get_constraints
│   ├── doctor.py           # doctor
│   ├── _config_dispatch.py # config-aware tool selection
│   └── _sources.py         # .f filelist expansion
└── adapters/               # one module per EDA tool: run it, parse its output
    ├── verilator.py  icarus.py  ghdl.py  cocotb_runner.py
    ├── verible.py  svlint.py
    ├── yosys.py  nextpnr.py  openfpgaloader.py  serial_capture.py
    ├── sby.py  eqy.py
    ├── vcs.py  questa.py  xcelium.py  vivado.py  quartus.py  dc_shell.py
    ├── jaspergold.py  vc_formal.py  spyglass.py  verdi.py
    ├── _sim_output.py      # collecting VCDs a simulation writes
    ├── _script_paths.py    # rejecting unsafe values in generated tool scripts
    └── _hints.py           # per-platform install hints
```

The Claude Code plugin is in `plugin/`: its manifest
(`plugin/.claude-plugin/plugin.json`), the server launch command
(`plugin/.mcp.json`) and its skill. The marketplace manifest stays at the
repository root (`.claude-plugin/marketplace.json`) and points at `./plugin`,
so installing the plugin copies only that directory.

Adapter conventions (binary lookup, environment, result shape, tests) are in
[CONTRIBUTING.md](../CONTRIBUTING.md) and the docstring of
`silica/adapters/__init__.py`.
