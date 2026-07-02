# Silica — Internal Code Review (`audit/findings`)

Read-only audit of `silica/server.py`, `silica/tools/`, `silica/adapters/`, `silica/skills/`,
`examples/`, and `pyproject.toml`, plus supporting infra (`config.py`, `oss_cad_suite.py`,
`_config_dispatch.py`, `cli.py`, `setup.py`, `terminal.py`, registries) and the `tests/` suite
to establish test-lock status. Nothing was modified.

**Test-lock legend:**
- **LOCKED** — an existing test asserts the current behavior; the proposed fix would change that test.
- **unlocked** — no test constrains this; safe to change without touching a test contract.

Severity: critical / high / medium / low.

---

## 1. Input handling & subprocess hygiene

All subprocess calls pass argv as a **list** (never `shell=True`, never a formatted shell string),
so there is **no OS-command-injection surface** in any adapter. The real exposure is (a) **tool-script
injection** where MCP-supplied file paths are interpolated into Yosys/TCL/sby/eqy scripts, and
(b) **no project-directory confinement** on the file tools.

| # | Issue | File:line | Sev | Test-lock | Proposed fix |
|---|---|---|---|---|---|
| 1.1 | ✅ **FIXED** (`bb78849`) — **No path confinement in `write_rtl`** — `dry_run=False` resolves any absolute/`..` path and writes it (`mkdir(parents=True)` + `write_text`), so a crafted `file` can create/overwrite arbitrary files anywhere the process can write. | `tools/project.py:94`, `:123-124` | **high** | **LOCKED** — `test_write_rtl_actually_writes` writes to `tmp_path` (outside cwd); confining to a root would break it | Add an optional project-root boundary check; resolve and reject paths that escape a configured root, or require the caller to pass an allowed root. Needs API/test sign-off. |
| 1.2 | ✅ **FIXED** (`bb78849`) — **No path confinement in `read_rtl` / `get_constraints`** — arbitrary absolute path read (returns full file contents), no root check. | `tools/project.py:57`, `:189` | medium | **LOCKED** — `test_read_rtl_missing_file` passes `/nonexistent/...`; tests assume unrestricted paths | Same boundary approach as 1.1; treat as read exfiltration surface. Needs sign-off. |
| 1.3 | ✅ **FIXED** (`91c342f`) — **Filename → Yosys script injection** — file paths are interpolated into the yosys `-p` command string as `read_verilog -sv "{f}"`; a path containing `"` or `;` breaks out and injects arbitrary yosys commands. | `adapters/yosys.py:83-86`, `:96` | medium | unlocked | Write the script to a temp `.ys` file and pass filenames via a mechanism that escapes quotes, or validate/reject paths containing quotes/semicolons/newlines. |
| 1.4 | ✅ **FIXED** (`91c342f`) — **Filename → TCL brace injection** (Vivado/Quartus/DC Shell/SpyGlass/JasperGold/VC Formal) — paths wrapped in `{...}`/`{{{f}}}`; a `}` or newline in the path escapes the braces and injects TCL. | `adapters/vivado.py:55-56`, `quartus.py:39-42`, `dc_shell.py:42-49`, `spyglass.py:50`, `jaspergold.py:26`, `vc_formal.py:22` | medium | unlocked | Sanitize/escape paths before interpolation, or reject paths with TCL metacharacters. |
| 1.5 | ✅ **FIXED** (`91c342f`) — **Filename → sby/eqy script injection** — interpolated into generated `.sby`/`.eqy`/`.ys` config bodies (`read -formal "{...}"`, basenames into `[files]`). Newline/quote in a path injects config directives. | `adapters/sby.py:185-189`, `eqy.py:135-138`, `:216-217` | low | unlocked | Escape or validate; the eqy Windows fallback (`_run_yosys_equiv`) has the same shape as 1.3. |
| 1.6 | ✅ **FIXED** (`92b21fd`) — **Unpinned deps** — `mcp>=1.9.0,<2.0.0` is bounded (ok), but `tomli-w>=1.0.0` has no upper bound. Dev deps declared **twice and inconsistently** (`[project.optional-dependencies].dev` pins pytest>=8.0/pytest-asyncio>=0.23; `[dependency-groups].dev` pins pytest>=9.1.1/pytest-asyncio>=1.4.0). | `pyproject.toml:22-24`, `:26-31`, `:53-57` | low | unlocked | Add upper bound to `tomli-w`; consolidate the two dev-dependency declarations into one. |
| 1.7 | **Hardcoded secrets/tokens** — none found. URLs and vendor links only. | — | — | — | No action. |

---

## 2. Correctness bugs

| # | Issue | File:line | Sev | Test-lock | Proposed fix |
|---|---|---|---|---|---|
| 2.1 | ✅ **FIXED** (`338fd4d`) — **Timeout handling is inconsistent across adapters** (the known issue). On `subprocess.TimeoutExpired`, some adapters return a structured error dict; the rest let the exception propagate out of the MCP tool call (uncaught crash). **Return dict:** `sby`, `eqy`, `nextpnr`, `openfpgaloader`. **Propagate:** `verilator`, `icarus`, `ghdl`, `yosys`, `vivado`, `quartus`, `dc_shell`, `vcs`, `questa`, `xcelium`, `jaspergold`, `vc_formal`, `spyglass`, `verible`, `svlint`. | e.g. `sby.py:106` / `eqy.py:97` / `nextpnr.py:117` / `openfpgaloader.py:52` vs `verilator.py:115`, `yosys.py:99`, `icarus.py:83`, `ghdl.py:73`, `vivado.py:98`, `quartus.py:86`, `dc_shell.py:77`, `vcs.py:61`, `xcelium.py:61`, `jaspergold.py:77`, `vc_formal.py:63`, `spyglass.py:85` | **high** | **LOCKED — both sides** — `test_timeout`/`test_timeout_returns_error` assert a dict for sby/eqy/nextpnr/openfpgaloader; `test_timeout_propagates` asserts `pytest.raises(TimeoutExpired)` for verilator/icarus/ghdl/yosys/vivado/quartus/dc_shell/vcs/xcelium/jaspergold/vc_formal/spyglass | Standardize on returning a structured error dict everywhere (a hang shouldn't crash the server). This **rewrites the `test_timeout_propagates` contract in 12 adapters** — needs sign-off. |
| 2.2 | ✅ **FIXED** (`b20b8e8`) — **`questa` `vlib work` has no `timeout=` and its return code is ignored** — if `vlib` hangs the whole call hangs unbounded; if it fails, compilation proceeds against a missing lib and the real error is obscured. | `adapters/questa.py:60-66` | medium | unlocked | Pass `timeout=` and check/report the `vlib` return code. |
| 2.3 | ✅ **FIXED** (`111d7a0`) — **3 of 4 registered MCP prompts return empty strings** — `server.py` registers `write_testbench`, `generate_assertions`, `close_timing`, but only `skills/workflows/debug_simulation_failure.md` exists. `_load_skill` returns `""` for missing files, so these prompts silently yield nothing. `skills/README.md` documents all four as if present. | `server.py:26-41`; missing `skills/workflows/{write_testbench,generate_assertions,close_timing}.md` | **high** | unlocked (no server/prompt tests exist) | Author the three missing skill files, or make `_load_skill` raise/log on a missing registered skill instead of returning `""`. |
| 2.4 | ✅ **FIXED** (`e528cab`) — **`config.load()` swallows all exceptions and returns shared mutable defaults** — a malformed `config.toml` is silently ignored (no log), masking user misconfig. Worse, it returns the module-level `_DEFAULTS` object directly (not a copy); a caller mutating nested dicts corrupts defaults process-wide. | `config.py:28-29`, `:22-23` | medium | unlocked | Narrow the `except` (e.g. `tomllib.TOMLDecodeError`, `OSError`), log the failure, and return a deep copy of defaults. |
| 2.5 | ✅ **FIXED** (`e528cab`) — **`_DEFAULTS` omits `place_route` and `program`** categories that exist in `CATEGORIES`. Currently masked because `pick()` falls back to `_FALLBACK`, but the defaults are internally inconsistent and a latent trap. | `config.py:9-19` vs `tools_registry.py:259` | low | unlocked | Add `place_route` and `program` to `_DEFAULTS.tools`, or derive it from `CATEGORIES`. |
| 2.6 | ✅ **FIXED** (`6566df8`) — **`__version__` disagrees with package version** — `__init__.py` says `0.1.0`, `pyproject.toml` says `0.1.4`. | `silica/__init__.py:1` vs `pyproject.toml:7` | low | unlocked | Single-source the version (read from metadata) or bump `__init__`. |
| 2.7 | ✅ **FIXED** (`6ee5f67`) — **Trace temp dirs leak on the compile-failure path** — `trace=True` creates a persistent `silica_trace_*` dir *before* compiling; if compile fails the function returns without ever cleaning or returning that dir. Repeated failing traced runs accumulate temp dirs. Affects verilator/icarus/ghdl/vcs/questa. | `verilator.py:90` (+early return `:125-134`), `icarus.py:69`, `ghdl.py:68`, `vcs.py:45`, `questa.py:57` | low | unlocked | Create the trace dir only after a successful compile, or clean it up on the failure return. |
| 2.8 | ✅ **FIXED** (`5245b27`) — **`search_rtl` reports `match_count` over all matches but returns only the first 50** — a caller acting on `match_count` sees a number that doesn't match `len(matches)`. | `tools/project.py:177` | low | **LOCKED** — `test_search_rtl_no_matches` asserts `match_count == 0` and `matches == []` (fix must preserve the empty case) | Return a `truncated: bool` flag, or rename to `total_matches` and document the 50-cap. |
| 2.9 | ✅ **FIXED** (`653cc57`) — **`eqy` Windows fallback selects `equiv_induct -seq 20` unconditionally** — a fixed induction depth silently caps proof strength; deep sequential inequivalences can be reported as UNKNOWN with no signal to the caller. | `adapters/eqy.py:161` | low | unlocked | Surface the depth in the result, or make it a parameter. |
| 2.10 | ✅ **FIXED** (`3168baa`) — **`nextpnr`/`vivado`/`quartus` treat exit 0 as success even if parsing found nothing** — utilization/timing come back all-zero when the report format doesn't match the regex, indistinguishable from a genuinely empty design. | `nextpnr.py:129-140`, `vivado.py:124-133`, `quartus.py:115-124` | low | unlocked | When rc==0 but no metrics parsed, add a warning noting the report couldn't be parsed. |

---

## 3. Layering violations

The intended layering is **tools → adapters → (oss_cad_suite / hints)**. Adapters should not import
from the `tools` package.

| # | Issue | File:line | Sev | Test-lock | Proposed fix |
|---|---|---|---|---|---|
| 3.1 | ✅ **FIXED** (`58c317b`) — **Adapters import upward into the tools layer** — 10 commercial adapters do `from silica.tools._config_dispatch import resolve`, i.e. the adapter (lower) layer reaches into `silica.tools` (upper). | `spyglass.py:8`, `vcs.py:8`, `questa.py:8`, `xcelium.py:8`, `vc_formal.py:9`, `jaspergold.py:9`, `verdi.py:5`, `vivado.py:8`, `dc_shell.py:8`, `quartus.py:8` | medium | unlocked (no test asserts the import path) | Move `resolve()`/`_BINARY` out of `tools/_config_dispatch.py` into a lower shared module (e.g. `silica.detect` or `oss_cad_suite`), and have both tools and adapters import from there. |
| 3.2 | **Adapters do NOT know about MCP** — verified clean; no adapter imports `mcp`/FastMCP. | — | — | — | No action (positive finding). |

---

## 4. Consistency (deviations from `shutil.which()` → build command → parse output)

| # | Issue | File:line | Sev | Test-lock | Proposed fix |
|---|---|---|---|---|---|
| 4.1 | ✅ **FIXED** (`58c317b`) — **Two parallel detection helpers** — OSS adapters detect via `oss_cad_suite.which()`; commercial adapters detect via `_config_dispatch.resolve()`. `resolve()` internally also consults `oss_cad_suite`, so the two overlap and can drift. | OSS: `verilator.py:31`, `icarus.py:61`, `yosys.py:77`, `ghdl.py:58`, `sby.py:33`, `nextpnr.py:75`, `eqy.py:17`, `openfpgaloader.py:29` vs commercial `resolve()` calls | medium | unlocked | Consolidate on one detection entry point (ties into 3.1). |
| 4.2 | ✅ **FIXED** (`6337e79`) — **`verible` and `svlint` bypass both helpers** — call `shutil.which()` directly (and `svlint` imports `shutil` *inside* `run()` at line 51). Other lint adapter `spyglass` uses `resolve()`. Inconsistent within the same category. | `verible.py:35`, `svlint.py:51` | low | unlocked | Route through the shared detector; hoist the `svlint` import to module top. |
| 4.3 | ✅ **FIXED** (`6337e79`, documented convention) — **`env=` handling differs** — OSS adapters pass `env=oss_cad_suite.env_with_suite()`; commercial and `verible`/`svlint` pass no `env`. Defensible (commercial tools aren't in the suite) but undocumented and easy to get wrong for a new adapter. | verible/svlint/all commercial `subprocess.run` calls | low | unlocked | Document the convention, or always pass an explicit env. |
| 4.4 | ✅ **FIXED** (`6337e79`, documented the inline exception) — **Waveform launch is split** — `launch_waveform` handles OSS viewers inline via `subprocess.Popen` (`waveform.py:61`) but delegates `verdi` to an adapter (`verdi.py`). Surfer/GTKWave have no adapter module while every other tool does. | `tools/waveform.py:50-61` | low | unlocked | Add `surfer`/`gtkwave` adapter modules for symmetry, or document the inline exception. |
| 4.5 | ⏸️ **SKIPPED** (entangled with the pending 5.1 `is_enabled()` decision — unifying the readers means touching or removing `is_enabled()`) — **`_config_dispatch.pick()` reads `priority` or `enabled`; `is_enabled()` reads only `enabled`** — two slightly different config-shape readers. | `_config_dispatch.py:85`, `:97-103` | low | unlocked | Unify the config-access helpers. |

---

## 5. Dead code / TODOs / incomplete stubs

| # | Issue | File:line | Sev | Test-lock | Proposed fix |
|---|---|---|---|---|---|
| 5.1 | ⏸️ **SKIPPED** (per instruction — decision pending on delete vs. wire into dispatch) — **`is_enabled()` is dead in production** — referenced only by `test_config_dispatch.py`; no tool or adapter calls it. | `_config_dispatch.py:97-103` | low | **LOCKED** — `test_is_enabled_*` cover it; removing it deletes those tests | Remove the function and its tests, or wire it into `pick()`/dispatch where selection is enforced. |
| 5.2 | ✅ **FIXED** (`c84730d`) — **Unused imports in `eqy.py`** — `import os` and `import shutil` are never used. | `adapters/eqy.py:3`, `:5` | low | unlocked | Remove. (Not caught automatically — `ruff` is configured but not installed in this env.) |
| 5.3 | ✅ **FIXED** (`c84730d`) — **Unused `import tempfile` in `jaspergold.py` and `vc_formal.py`** — both also `from tempfile import mkdtemp`; only `mkdtemp` is used, the plain module import is dead. | `jaspergold.py:5`, `vc_formal.py:5` | low | unlocked | Drop the redundant `import tempfile`. |
| 5.4 | ✅ **FIXED** (`c84730d`) — **Unused imports in `clients_registry.py`** — `import sys` and `import shutil` are never used. | `clients_registry.py:2-3` | low | unlocked | Remove. |
| 5.5 | ✅ **FIXED** (`111d7a0`) — **Incomplete skills set** — see 2.3; three registered prompts have no file. `skills/README.md` also lists them as existing. | `skills/README.md:12-16` | (rolled into 2.3) | unlocked | Add files or fix README + registration. |
| 5.6 | **No explicit `TODO`/`FIXME`/`XXX`/`pass`-stub markers found** in scope. | — | — | — | No action. |

---

## 6. Test coverage gaps

| # | Gap | Where | Sev | Notes / proposed test |
|---|---|---|---|---|
| 6.1 | ✅ **FIXED** (`111d7a0`) — **`server.py` has zero tests** — no `test_server.py`; prompt registration, `_load_skill`, and the empty-string-on-missing-file behavior (2.3) are entirely uncovered. | `server.py` | high | Add a test asserting each registered prompt returns non-empty content — this would have caught 2.3. |
| 6.2 | ✅ **FIXED** (`bb78849`) — **No path-escape / confinement tests** for `read_rtl`/`write_rtl`/`get_constraints`. Existing tests actively rely on unrestricted absolute paths, so confinement (1.1/1.2) is untested *and* pre-locked against. | `tests/test_tool_project.py` | high | Once a boundary is decided, add tests for `..`/absolute escapes; will require reworking current tmp_path-based tests. |
| 6.3 | ✅ **FIXED** (`b20b8e8`) — **`questa` `vlib` no-timeout / rc-ignored path (2.2) untested.** | `tests/test_adapter_questa.py` | medium | Add a `vlib`-failure and `vlib`-hang case. |
| 6.4 | ✅ **FIXED** (`91c342f`) — **Script/brace-injection behavior (1.3–1.5) untested** — no test feeds a path containing `"`, `}`, `;`, or newline. | adapter tests | medium | Add fuzz-style cases with metacharacter paths asserting they're escaped/rejected. |
| 6.5 | ✅ **FIXED** (`e528cab`) — **`config.load()` malformed-file / defaults-aliasing (2.4) untested.** | `tests/test_config.py` | low | Add a corrupt-TOML case and an assertion that returned defaults are independent copies. |
| 6.6 | ✅ **FIXED** (`ac10afd`) — **`terminal.py` (hyperlink/OSC-8 detection) appears untested.** | `terminal.py` | low | Add unit tests for `supports_hyperlinks()` env-matrix and `hyperlink()` fallback. |
| 6.7 | ✅ **FIXED** (`6ee5f67`) — **Trace-dir leak on compile failure (2.7) untested** — traced-run tests don't assert temp-dir cleanup. | sim adapter tests | low | Assert no `silica_trace_*` dir survives a failed traced compile. |

---

## Summary

**Remediation status (2026-07-01):** every actionable item is **FIXED** except two **SKIPPED**
pending a decision — **5.1** (`is_enabled()` delete-vs-wire-into-dispatch) and **4.5** (config-reader
unification, entangled with 5.1). Each table row above carries its status and the commit hash it
landed in. Verified by: full test suite (399 passed, 9 environment skips), ruff (remaining findings
are pre-existing style debt — long lines, f-string/import-sort nits — not introduced by these fixes),
and a live `run_simulation` + `lint` run against `examples/uart` (all 5 testbench bytes PASS).

**Total issues: 30** (positive findings 1.7 and 3.2 excluded from counts).

By severity:
- **critical:** 0
- **high:** 5 — 1.1 (write path escape), 2.1 (timeout inconsistency), 2.3 (missing skill files), 6.1 (server untested), 6.2 (no confinement tests)
- **medium:** 9 — 1.2, 1.3, 1.4, 2.2, 2.4, 3.1, 4.1, 6.3, 6.4
- **low:** 16 — 1.5, 1.6, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 6.5, 6.6, 6.7 (5.5 folded into 2.3)

### Safe / independent to fix (no test contract or MCP API change)
These touch no existing test assertion and no tool signature — fix freely:
- **2.3 / 5.5** — author the three missing skill files (`write_testbench`, `generate_assertions`, `close_timing`) and fix README. *(highest-value quick win)*
- **2.6** — version mismatch.
- **5.2, 5.3, 5.4** — remove unused imports (`eqy`, `jaspergold`, `vc_formal`, `clients_registry`).
- **2.4, 2.5** — `config.load()` exception narrowing + defaults copy; complete `_DEFAULTS`.
- **2.7** — trace-dir leak on compile failure.
- **2.2** — `questa` `vlib` timeout + rc check.
- **1.3, 1.4, 1.5** — escape/validate filenames in generated Yosys/TCL/sby/eqy scripts.
- **4.2, 4.4, 4.5** — consistency cleanups (verible/svlint detection, waveform symmetry, config readers).
- **6.1, 6.3, 6.4, 6.5, 6.6, 6.7** — add the missing tests.

### Needs your sign-off first (touches a test contract or the MCP tool API surface)
- **2.1 (high)** — harmonizing timeout behavior rewrites `test_timeout_propagates` in **12 adapters**. Decide the target contract (recommend: all adapters return a structured error dict; a hang must not crash the server).
- **1.1 / 1.2 (high/medium)** — adding project-directory confinement to `write_rtl`/`read_rtl`/`get_constraints` changes the file-tool behavior and **breaks the current `tmp_path`-based tests** (6.2). Decide whether confinement is desired and what the root boundary is; this is an intentional-behavior/API decision.
- **3.1 / 4.1 (medium)** — moving `resolve()`/`_BINARY` out of `tools/` into a shared lower module is a refactor across 10 adapters; low risk but broad, so flagging before touching import paths.
- **5.1 (low)** — removing `is_enabled()` deletes its two tests; alternatively wire it into dispatch (a behavior change). Your call on which direction.

### Sign-off resolutions applied
- **2.1** — standardized: all adapters return a structured error dict on timeout (`338fd4d`).
- **1.1/1.2** — confinement added: file tools reject paths escaping the server's working directory (`bb78849`).
- **3.1/4.1** — `resolve()`/`_BINARY` moved to the new lower-layer `silica.detect` module (`58c317b`).
- **5.1** — skipped per instruction; see the pending question on what `is_enabled()` is for.
