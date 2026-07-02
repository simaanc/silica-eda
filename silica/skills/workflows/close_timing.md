# Skill: Close Timing

**Task**: Work a design from failing timing (negative WNS) to closure through targeted RTL and constraint changes — not blind pipelining.

**When to use**: `synthesize()` or `run_place_route()` returns `timing_summary.wns < 0` or `failing_endpoints > 0`, or the user asks to hit a clock frequency.

---

## Reasoning Script

### Step 1 — Establish the real numbers

Run `synthesize(top_module, files, target=...)` and read `timing_summary`:
- `wns` — worst negative slack, ns. The single worst path. Closure means `wns >= 0`.
- `tns` — total negative slack. `tns ≈ wns × small N` → a few bad paths (surgical fix). `|tns| >> |wns|` with many `failing_endpoints` → structural problem (whole design too slow for the clock).
- Post-synthesis timing is an estimate; only place-and-route timing (`run_place_route`) includes real routing delay. Close synthesis timing with margin (~10–15%) before trusting it.

If the tool is Yosys with a generic target, there is no real timing model — use an FPGA target (`ice40`, `ecp5`, `xilinx`) or a commercial tool for meaningful numbers.

### Step 2 — Check the constraints before touching RTL

Call `get_constraints(file)` on the project's `.xdc`/`.sdc`. Verify:
- The clock is actually created (`create_clock -period ...`) and the period matches the target frequency — a missing constraint means the tool optimized for nothing
- False paths / multicycle paths are declared where the design intent allows (CDC synchronizers, quasi-static config registers)
- No over-constraint: a 5 ns period requested where 10 ns is needed guarantees failure noise that hides real paths

An unconstrained or wrongly-constrained design fails timing for free. Fix constraints first; re-run; only then read paths.

### Step 3 — Identify the failing path structure

From `raw_output`, find the worst path's start/endpoint and the logic-levels count. Classify:

| Path signature | Root cause | Fix family |
|---|---|---|
| Many logic levels (>8–10) between FFs | Too much combinational work per cycle | Pipeline: split with a register stage |
| Wide arithmetic (adders ≥ 32b, multipliers, comparators) | Carry chains | Retime, use DSP blocks, split add over 2 cycles |
| Large mux / priority chain (long `if/else if`, casez) | Priority logic depth | Recode as parallel `case`/one-hot; balance the tree |
| High-fanout net (enable, reset, state bit) | Net delay, not logic | Register duplication, `max_fanout`, synchronous reset tree |
| Path crosses clock domains | Not a real path | `set_false_path` / proper CDC, never "fix" with pipelining |
| End at RAM/DSP with extra logic | Missed hard-block inference | Restructure to match inference template; enable output register |

### Step 4 — Apply the smallest structural fix

Priority order — cheapest and least invasive first:
1. Constraint fix (false/multicycle path that reflects true intent)
2. Recode the critical expression (priority → parallel, strength-reduce `%`/`*` by constants, compare against constant instead of subtract)
3. Retime: move logic across an existing register boundary
4. Add a pipeline stage — last resort, because it changes latency and every consumer of the interface

Propose via `write_rtl(dry_run=True)`; after applying, re-run `run_simulation` (functional check — pipelining changes latency, so the TB may need updating) then `synthesize`.

### Step 5 — Iterate on the *new* worst path

After each fix re-read `wns`/`tns`/`failing_endpoints`. Expect the worst path to move somewhere else; repeat Steps 3–4. Stop when `wns >= 0` with margin, or when successive iterations improve WNS by <5% — that's the architecture's wall, and the honest answer is a lower clock target or a bigger restructure.

### Step 6 — Report

State: starting WNS/TNS → final WNS/TNS, each change made and the slack it bought, remaining risk (post-route margin, latency changes that affect interfaces).

---

## Few-Shot Examples

### Example 1 — Priority chain in an address decoder

**Context**: `synthesize("mem_ctrl", files, target="xilinx", tool="vivado")` returns:
```json
{
  "exit_code": 0,
  "timing_summary": {"wns": -1.82, "tns": -9.4, "failing_endpoints": 5},
  "utilization": {"luts": 3410, "ffs": 2100, "lut_pct": 16.4, "ff_pct": 5.0}
}
```
`raw_output` worst path: `araddr_reg[31]` → `slave_sel_reg[6]`, 14 logic levels.

**Correct reasoning**:
1. `tns/wns ≈ 5` with 5 endpoints — one localized structure, all endpoints in `slave_sel`. Surgical case.
2. 14 logic levels at ~0.35 ns/level explains the miss; the decoder is the problem, not the clock.
3. `read_rtl("mem_ctrl.sv")` shows a 7-branch `if/else if` chain comparing 32-bit `araddr` ranges → serial priority logic.
4. Fix: ranges are mutually exclusive, so recode as parallel per-slave comparators:
```diff
-    if (araddr < 32'h1000)            slave_sel <= 7'b0000001;
-    else if (araddr < 32'h2000)       slave_sel <= 7'b0000010;
-    ...
+    // ranges are disjoint — decode in parallel, one comparator pair per slave
+    slave_sel[0] <= (araddr[31:12] == 20'h00000);
+    slave_sel[1] <= (araddr[31:12] == 20'h00001);
+    ...
```
Note the recode also replaced range compares with equality on the upper bits — cheaper and faster.
5. Re-run: `wns: +0.31`, `failing_endpoints: 0`. Re-run simulation → `PASS` (no latency change, safe).

### Example 2 — Structural failure: 48-bit accumulate at 200 MHz

**Context**: `synthesize("dsp_acc", files, target="ice40", tool="yosys")` then `run_place_route(...)`:
```json
{"timing_summary": {"wns": -4.1, "tns": -310.2, "failing_endpoints": 96}}
```

**Correct reasoning**:
1. `|tns| >> |wns|`, 96 endpoints — structural, not surgical. The design misses everywhere.
2. Worst paths all end in `acc_reg[*]`: a 48-bit add-accumulate closes nowhere near 5 ns on iCE40 carry logic (~65 MHz realistic).
3. Constraint check first: `.pcf`/SDC requests 200 MHz — is that a hard requirement? Input data arrives at 50 MS/s, so the accumulator does **not** need 200 MHz.
4. Cheapest real fix is architectural: run the accumulator in the 50 MHz domain (data rate), keep only the narrow output interface at 200 MHz — or split the 48-bit add into two 24-bit stages with a pipelined carry if it must stay at 200 MHz (adds 1 cycle latency; TB updated accordingly).
5. Domain split applied → `wns: +1.7` at 50 MHz for the accumulator, 200 MHz domain now trivially clean. Report explicitly: latency and interface unchanged, one new CDC (properly synchronized, `set_false_path` on the sync chain).

---

## Edge Cases

- **WNS = 0.0 with 0 endpoints and near-zero utilization**: usually means no timing constraints were applied or parsing found nothing — treat as "no data", not "timing met". Check for a `create_clock` before celebrating.
- **Negative slack only on paths into synchronizer FFs**: those are CDC paths; the fix is `set_false_path`/`set_max_delay -datapath_only`, never pipelining (which just delays the metastability window).
- **Pipelining valid/ready interfaces**: adding a stage on data without stalling logic breaks the handshake — a skid buffer is required, not a bare register.
- **Post-synthesis pass, post-route fail**: routing congestion; look at utilization (>80% LUT often trades directly against routability) before blaming logic depth.
- **`-retiming`/`opt_ff` tool options**: cheap to try before RTL surgery, but confirm the tool actually moved registers (report diff), and never rely on retiming across reset-value-asymmetric FFs.
