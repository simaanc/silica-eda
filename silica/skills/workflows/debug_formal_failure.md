# Skill: Debug Formal Failure

**Task**: Triage a failing formal run end-to-end — from `run_formal()` status to a verified fix, using the counterexample trace as evidence.

**When to use**: Any time `run_formal()` returns `status` of `"FAIL"`, `"UNKNOWN"`, or `"ERROR"`.

---

## Reasoning Script

Follow these steps in order. The single most common mistake is treating every FAIL as an RTL bug — roughly half of formal failures are environment problems (missing assumptions) or badly written properties.

### Step 1 — Classify by status

| Status | Meaning | Next step |
|---|---|---|
| `FAIL` | Solver found a concrete counterexample | Step 2 — read the trace before guessing |
| `UNKNOWN` | Solver gave up: bound too shallow, induction not closed, or timeout | Step 6 |
| `ERROR` | Setup problem: syntax error, missing file, elaboration failure | Read `errors` list; fix the config/RTL and re-run — this is not a design bug |

### Step 2 — Read the failing property

`failures` gives `{module, property, file, line}`. Call `read_rtl(file, start_line=line-10, end_line=line+5)` and answer:

- What exactly does the assertion claim?
- Is it guarded against reset and initial state (`f_past_valid`-style guards for `$past`)?
- What signals appear in the property? These are what you will pull from the trace.

### Step 3 — Read the counterexample trace

The counterexample VCD in `traces[0]` shows the exact scenario the solver found. The violation is at the **last timestep** of the trace.

1. `read_waveform(traces[0])` — discover signal names and `end_time`.
2. `read_waveform(traces[0], signals=[...], time_start=0, time_end=end_time)` — counterexample traces are short (≤ the proof depth), so read the whole thing for every signal in the property, plus clock, reset, and state registers.

### Step 4 — Classify the root cause

Walk the trace forward from `t=0` and decide which of these you are looking at:

| Evidence in trace | Root cause | Fix |
|---|---|---|
| Reset never asserted, or registers start at impossible values (e.g. one-hot FSM in state `00…0`) | **Unconstrained initial state** — the solver starts anywhere the netlist allows | Add `assume` for reset/initial conditions, or `initial` value on the register |
| Inputs do something the real environment never would (both `req` and `flush` in the same cycle, data changes mid-handshake) | **Missing environment assumption** | Add `assume property` encoding the interface contract |
| Trace is realistic and the design genuinely misbehaves | **Real RTL bug** | Fix the RTL |
| Design behaves fine but the property fires anyway | **Wrong property** | Fix the assertion (off-by-one in `$past` depth, missing guard, wrong operator) |

### Step 5 — Fix and verify

- RTL fix: `write_rtl(file, new_content, dry_run=True)` first, then apply.
- Assumption fix: add the `assume` inside the `` `ifdef FORMAL `` block, and sanity-check it isn't so strong it makes the proof vacuous — re-run with `mode="cover"` on a reachability cover for the guarded state if in doubt.
- Re-run `run_formal()` with the same arguments. PASS confirms the fix.

### Step 6 — UNKNOWN: depth and induction problems

- `mode="bmc"` UNKNOWN: the bound was too shallow to reach anything interesting. Raise `depth` (bugs are usually shallow; if 40–60 cycles finds nothing, the property is probably fine at BMC depth).
- `mode="prove"` UNKNOWN with base case passing: **k-induction failed to close** — the invariant is not inductive. Add helper assertions that pin down reachable state (relationships between counters, one-hot-ness of FSM state) so the induction step can't start from an unreachable state. `induction_failures` says which assertion the induction step broke; these are not reachable failures.
- On Windows, eqy equivalence falls back to bounded induction and echoes `induction_depth`; UNKNOWN there may just mean the bound was too shallow — raise `depth` before concluding anything.
- Timeout (`"timed out"` in errors): raise `timeout`, reduce `depth`, or try another engine (`engine="smtbmc bitwuzla"`).

### Step 7 — Root cause summary

- Verdict: RTL bug / missing assumption / wrong property / depth issue (one sentence)
- Evidence: what the counterexample trace showed, with signal values and times
- Fix applied and re-run result

---

## Few-Shot Examples

### Example 1 — Counterexample from unconstrained initial state

**Context**: 4-bit counter with a wrap-around assertion; `mode="prove"`.

**`run_formal()` output:**
```json
{
  "status": "FAIL",
  "rc": 2,
  "failures": [
    {
      "module": "counter",
      "property": "assert_no_overflow",
      "file": "rtl/counter.sv",
      "line": 42
    }
  ],
  "traces": ["/tmp/silica_sby_counter/engine_0/trace.vcd"],
  "warnings": [],
  "errors": [],
  "workdir": "/tmp/silica_sby_counter"
}
```

**`read_rtl("rtl/counter.sv", start_line=32, end_line=45)`:**
```
  32    always_ff @(posedge clk) begin
  33        if (rst)         count <= '0;
  34        else if (enable) count <= count + 1'b1;
  35    end
  36
  37    `ifdef FORMAL
  38        always_ff @(posedge clk) begin
  39            if (!rst && $past(!rst))
  40                // count only advances when enabled
  41                if (!$past(enable))
  42                    assert (count == $past(count));
  43        end
  44    `endif
```

**`read_waveform("/tmp/silica_sby_counter/engine_0/trace.vcd", signals=["clk", "rst", "enable", "count"], time_start=0, time_end=20)`:**
```json
{
  "timescale": "1ns",
  "end_time": 15,
  "signals": [
    {"name": "counter.rst",    "transitions": [{"time": 0, "value": "0"}]},
    {"name": "counter.enable", "transitions": [{"time": 0, "value": "0"}]},
    {"name": "counter.count",  "transitions": [{"time": 0, "value": "1010"},
                                               {"time": 10, "value": "1011"}]}
  ],
  "not_found": []
}
```

**Correct reasoning**:

1. The trace is two timesteps long. `rst` is **never asserted** and `count` starts at `1010` — an arbitrary value, then increments with `enable` low.
2. In real hardware, reset runs first. The solver is exploiting an unconstrained initial state: nothing forces `count` to a defined value before the assertion is checked. The `$past(!rst)` guard is not enough because reset never happens at all in this trace.
3. This is **not an RTL bug** — it is a missing constraint on the formal environment. Also note `count` incremented while `enable` was low in the trace: with an undefined start the solver may drive internals inconsistently before constraints bite.
4. Fix: constrain the initial state.

**Fix** (`write_rtl(dry_run=True)` diff):
```diff
 `ifdef FORMAL
+    // Solver may start anywhere — force reset while $past is invalid.
+    reg f_past_valid = 1'b0;
+    always_ff @(posedge clk) f_past_valid <= 1'b1;
+    always_comb if (!f_past_valid) assume (rst);
+
     always_ff @(posedge clk) begin
-        if (!rst && $past(!rst))
+        if (f_past_valid && !rst && $past(!rst))
```

**Verification**: `run_formal()` → `status: "PASS"`.

---

### Example 2 — Induction fails to close (UNKNOWN, base case passes)

**Context**: FIFO with `assert (count <= DEPTH)`; `mode="prove"`, `depth=20`.

**`run_formal()` output:**
```json
{
  "status": "UNKNOWN",
  "rc": 4,
  "failures": [],
  "traces": [],
  "induction_failures": [
    {"property": "fifo._witness_.check_assert_fifo_sv_41_3", "file": "fifo.sv", "line": 41}
  ],
  "induction_traces": ["/tmp/silica_sby_fifo/engine_0/trace_induct.vcd"],
  "warnings": [],
  "errors": [],
  "workdir": "/tmp/silica_sby_fifo",
  "raw_output": "... engine_0: induction: unsat failed at step 20 ... DONE (UNKNOWN, rc=4)"
}
```

**Correct reasoning**:

1. No counterexample and no failure — BMC (base case) passed, so no bug is reachable within 20 cycles. The **induction step** failed: starting from an arbitrary state satisfying the assertions, the solver can violate the property. `induction_failures` names the assertion it broke, and `induction_traces[0]` shows the (unreachable) starting state — useful for spotting which registers disagree.
2. The classic cause in a FIFO: `count`, `wr_ptr`, and `rd_ptr` are separate registers. In an *unreachable* state where `count` disagrees with the pointer difference, one more push wraps `count` past `DEPTH`. Induction starts from exactly such states unless an invariant excludes them.
3. Do not raise `depth` first — an invariant that isn't inductive stays non-inductive at depth 50. Add a helper assertion tying the redundant state together.

**Fix** (added inside the `` `ifdef FORMAL `` block):
```systemverilog
// Helper invariant: count always equals the pointer difference.
// This is what makes the DEPTH bound inductive.
always_comb assert (count == (wr_ptr - rd_ptr));
```

**Verification**: `run_formal()` → `status: "PASS"` — with the state pinned down, induction closes at the same depth.

---

## Edge Cases

- **Vacuous PASS after adding assumptions**: contradictory assumptions prove anything. After adding an `assume`, run `mode="cover"` on a state the design should reach; an unreachable cover means the assumptions are over-constrained.
- **`$past` in the first cycle**: `$past(x)` is undefined at time 0 and a top source of spurious FAILs. Every property using `$past` needs an `f_past_valid` guard.
- **Trace file is `.yw` not `.vcd`**: some engines emit Yosys witness files. Check `traces` entries end in `.vcd` before calling `read_waveform`; if only `.yw` exists, re-run with `engine="smtbmc z3"` which writes VCD traces.
- **Equivalence FAIL after synthesis-style rewrites**: check for `x`-propagation differences first (uninitialized registers optimized differently), not logic bugs.
- **Multiple failures listed**: fix the first one and re-run — later failures are often shadows of the first counterexample.
