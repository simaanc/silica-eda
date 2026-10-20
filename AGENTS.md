# AGENTS.md

Guidance for coding agents (Codex, Cursor and others that read `AGENTS.md`).

## Using silica's MCP tools

When the silica MCP server is connected, its own instructions, sent when the
connection starts, are the reference for how to use it: the tool order, what
each step passes to the next, and the known pitfalls. The same text is in
[`silica/skills/base/rtl_assistant.md`](silica/skills/base/rtl_assistant.md).
In short:

- Call `doctor` first to see which EDA tools are installed.
- Work in this order and stop at the first failure: `lint` → `run_simulation`
  → `run_formal` → `synthesize` → `run_place_route` → `program_device` →
  `capture_serial`.
- Call `write_rtl` with `dry_run=True` and show the diff before writing.
- Treat a formal `UNKNOWN` with `induction_failures` as inconclusive, not as a
  bug.
- Name the serial port explicitly. If access is denied, show the user the
  returned `fix` command; don't run `sudo` yourself.

## Working on this repository

- Setup: `uv sync`. Checks: `uv run ruff check silica/ tests/ scripts/` and
  `uv run pytest tests/ -q`. Integration tests skip themselves when an EDA
  tool isn't installed.
- Adapters live in `silica/adapters/` (one per tool) and MCP tools in
  `silica/tools/`; [CONTRIBUTING.md](CONTRIBUTING.md) has the conventions.
  Unit tests mock `subprocess.run` with output captured from the real tool.
- Every commit is signed off (`git commit -s`), one logical change each, with
  a Conventional Commits subject.
- Add a line under "Unreleased" in `CHANGELOG.md` for every user-visible
  change. Tool names, parameters and result fields follow the compatibility
  policy in the README.
- A new tool or prompt must also appear in the server instructions; a test
  checks this.
- Releases: see [RELEASING.md](RELEASING.md).
