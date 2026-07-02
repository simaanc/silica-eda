# Skill: Generate Assertions

**Task**: Translate design intent into SystemVerilog Assertions (SVA) and prove or falsify them with `run_formal()`.

**When to use**: The user asks for assertions, wants formal verification of a property ("this FIFO can never overflow", "grant is always one-hot"), or a bug is intermittent/hard to stimulate in simulation.

---

## Reasoning Script

### Step 1 — Extract the design intent

Read the DUT with `read_rtl(file)`. From the code and any comments, list candidate invariants in plain English first. Good sources:
- Handshake contracts (valid must hold until ready; ack only after req)
- Counter/pointer bounds (FIFO count ≤ DEPTH, state ∈ enum range)
- One-hot / mutual exclusion (grants, FSM state bits, tri-state enables)
- Liveness expectations (a request is eventually served)
- Interface stability (data stable while valid && !ready)

Write each as a sentence before writing any SVA. If you can't state it in a sentence, you don't understand it well enough to assert it.

### Step 2 — Classify each property

| Intent shape | SVA form | run_formal mode |
|---|---|---|
| "X is always true" | `assert property (@(posedge clk) disable iff (!rst_n) X);` | `prove` |
| "After A, B within N cycles" | `A |-> ##[1:N] B` | `bmc` first, then `prove` |
| "A eventually leads to B" | `A |-> s_eventually B` | `live` |
| "This state is reachable" | `cover property (...)` | `cover` |

Prefer implication (`|->` same cycle, `|=>` next cycle) over long sequences — small properties localize failures.

### Step 3 — Write the assertions

Conventions:
- Wrap assertions in a module-bound checker or an `ifdef FORMAL` block so synthesis ignores them
- Always `disable iff (!rst_n)` (match the DUT's reset) — reset-time `x` produces spurious counterexamples
- Label every property: `ast_no_overflow: assert property (...)` — labels are what `run_formal` reports back
- Add `assume property` for input constraints (e.g., inputs one-hot, no request during reset). Missing assumptions are the #1 source of false failures
- Add at least one `cover property` per assumption set to prove the assumed space is non-empty — an over-constrained proof passes vacuously

### Step 4 — Run bounded model check first

`run_formal(files=[dut_with_assertions], top=..., mode="bmc", depth=20)` — BMC finds shallow counterexamples in seconds. Only after BMC is clean, escalate to `mode="prove"` (k-induction; unbounded).

### Step 5 — Triage the result

- `status: "FAIL"` → `failures` lists the property labels; `traces` contains counterexample VCDs. Open with `launch_waveform(trace)`, walk the trace backwards from the violation cycle. Decide: RTL bug, wrong assertion, or missing assumption — in that order of suspicion only *after* checking the trace uses legal inputs. Illegal inputs in the trace → missing `assume`.
- `status: "UNKNOWN"` at prove → induction failed but no counterexample. Strengthen with helper invariants (assert internal relationships the inductive step needs, e.g., pointer difference equals count) or raise depth.
- `status: "PASS"` in bmc mode only means "no violation within depth" — say so explicitly, never report a bounded pass as a proof.

### Step 6 — Report

For each property: the English intent, the SVA, the verification status (proved / bounded-pass to depth N / falsified with trace path), and any assumptions the proof depends on.

---

## Few-Shot Examples

### Example 1 — FIFO can never overflow or underflow

**Intent**: "Count stays within [0, DEPTH]; no write-when-full is accepted, no read-when-empty returns data."

**Assertions added to `fifo.sv`**:
```systemverilog
`ifdef FORMAL
    ast_count_bound:  assert property (@(posedge clk) disable iff (!rst_n)
                          count <= DEPTH);
    ast_no_overflow:  assert property (@(posedge clk) disable iff (!rst_n)
                          (wr_en && full) |=> count == $past(count) - (rd_en && !empty));
    ast_full_def:     assert property (@(posedge clk) disable iff (!rst_n)
                          full == (count == DEPTH));
    cov_wrap:         cover  property (@(posedge clk) disable iff (!rst_n)
                          full ##[1:$] empty);   // fill then fully drain is reachable
`endif
```

**Run**: `run_formal(files=["fifo.sv"], top="fifo", mode="bmc", depth=20)`

**Output**:
```json
{
  "status": "FAIL",
  "failures": [{"property": "ast_count_bound", "file": "fifo.sv", "line": 84}],
  "traces": ["/tmp/silica_sby_gen_x1/fifo_bmc/engine_0/trace.vcd"]
}
```

**Trace analysis**: at cycle 17 `count == DEPTH` and a simultaneous `wr_en && rd_en` arrives. The RTL computes `count <= count + wr_en - rd_en` but gates the write pointer with `!full` and the read pointer with `!empty` — count and pointers disagree on the simultaneous case. Real RTL bug: the count update must use the same gated conditions (`(wr_en && !full)` / `(rd_en && !empty)`). After the fix, BMC passes; `mode="prove"` returns `status: "PASS"` — unbounded proof.

### Example 2 — Arbiter grant is one-hot and every request is served

**Intent**: "At most one grant at a time; a held request is granted within 4 cycles."

```systemverilog
`ifdef FORMAL
    ast_onehot:   assert property (@(posedge clk) disable iff (!rst_n)
                      $onehot0(grant));
    ast_latency:  assert property (@(posedge clk) disable iff (!rst_n)
                      req[i] |-> ##[1:4] grant[i]);
    asm_hold:     assume property (@(posedge clk) disable iff (!rst_n)
                      req[i] && !grant[i] |=> req[i]);   // requester holds until served
    cov_all_req:  cover  property (@(posedge clk) &req);
`endif
```

**Run**: BMC depth 20 → `PASS`. `mode="prove"` → `status: "UNKNOWN"` for `ast_latency`.

**Correct reasoning**: UNKNOWN ≠ FAIL. Induction can't see that the internal round-robin pointer cycles through all positions. Add a helper invariant (`ast_ptr_range: assert property (rr_ptr < N);`) and re-prove → `PASS`. Report: one-hot proved unconditionally; latency proved **under the hold assumption** `asm_hold`, and `cov_all_req` confirms the assumption doesn't empty the input space.

---

## Edge Cases

- **Vacuous passes**: an antecedent that can never be true "passes" trivially. Pair every non-trivial implication with a `cover` of its antecedent.
- **`$past` at cycle 0**: `$past(x)` is undefined on the first cycle — guard with `##1` after reset release or a `first_cycle` flag.
- **Multiple clocks**: sby's default flow is single-clock. Multi-clock properties need explicit clocking per assertion, and CDC properties generally need a commercial tool (`tool="jaspergold"` / `"vc_formal"`).
- **Liveness needs `mode="live"`**: `s_eventually` under prove/bmc is either rejected or bounded; only live mode checks true liveness — and it needs fairness assumptions on inputs.
- **Yosys `read -formal` subset**: some SVA (complex sequences, `throughout`, local variables) isn't supported by the open flow; if sby errors on parse, simplify the property or switch tools rather than weakening the intent.
