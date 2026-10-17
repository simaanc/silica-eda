# Contributing to silica

Thanks for helping. Bug reports, parser fixes for new tool versions, and new
adapters are all welcome.

## Development setup

You need [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer.

```bash
git clone https://github.com/simaanc/silica-eda
cd silica-eda
uv sync                          # editable install + dev deps (pytest, ruff)

uv run ruff check silica/ tests/
uv run pytest tests/ -q          # unit suite; integration tests self-skip
```

CI runs the same two commands on Linux and Windows for Python 3.11 to 3.14.
Please run them before opening a pull request.

## Integration tests

`tests/integration/` runs the adapters against real tool binaries. Each test
skips itself when its tool is missing. The easiest way to get them all is the
[OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases):

```bash
export SILICA_OSS_CAD_SUITE=/path/to/oss-cad-suite
uv sync --extra cocotb           # lets the cocotb test run
uv run pytest tests/integration/ -q -rs
```

The Integration workflow runs these weekly against the latest suite release.
Its job is to catch output-format drift in the tools, so when an adapter's
parser changes, add or update an integration test that uses real tool output.

## Adding or changing an adapter

Adapters live in `silica/adapters/` (one module per tool) and the MCP tools
that dispatch to them live in `silica/tools/`. The conventions are in the
docstring of `silica/adapters/__init__.py`. In short:

- Detect binaries through `silica.detect.resolve`, not `shutil.which`.
- Pass `env=oss_cad_suite.env_with_suite()` for tools the OSS CAD Suite
  bundles; commercial tools and standalone linters get the caller's
  environment unchanged.
- Check every value you interpolate into a generated script with
  `_script_paths.unsafe_script_value`.
- Return the same structured result dict as the other adapters of that kind,
  including on timeouts and missing binaries. Never raise into the server.
- Register a new tool in `silica/tools_registry.py` and give it install hints
  in `silica/adapters/_hints.py`. A test fails if the two drift apart.
- Unit tests mock `subprocess.run`. Base the mocked output on what the real
  tool prints, not on what you expect it to print.

## Commits and pull requests

- Sign off every commit with `git commit -s`. This adds a `Signed-off-by:`
  line certifying the [Developer Certificate of Origin](https://developercertificate.org):
  that you wrote the change or otherwise have the right to submit it under
  the project's license. A CI check rejects pull requests with unsigned
  commits; fix existing ones with `git rebase --signoff main`.
- Keep each commit to one logical change, with a
  [Conventional Commits](https://www.conventionalcommits.org/) subject line
  (`fix(eqy): ...`, `feat: ...`, `docs: ...`) and a body that says why.
- Open pull requests against `main`. CI must pass before merging.
- Add a line under "Unreleased" in `CHANGELOG.md` for anything user-visible.

## Reporting bugs and security issues

Use the issue templates for bugs and feature requests. Report security
vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

By contributing you agree that your work is licensed under the project's
[AGPL-3.0-only license](LICENSE), and you agree to follow the
[code of conduct](CODE_OF_CONDUCT.md).
