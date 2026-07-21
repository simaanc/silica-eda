# Skill: Debug Simulation Failure

**Task**: Triage a failing simulation end-to-end — from raw error output to a verified RTL fix.

**When to use**: Any time `run_simulation()` returns `exit_code != 0` or the simulation completes but produces wrong output / assertion failures.

---

## Reasoning Script

Follow these steps in order. Do not skip to hypothesis before completing the diagnostic phase.

### Step 1 — Classify the failure mode

Look at the `errors` list from `run_simulation()`. Classify each error:

| Error pattern | Category | Next step |
|---|---|---|
| `%Error-PARSE`, `syntax error` | Syntax error | Read the flagged line; fix syntax |
| `%Error-BLKSEQ`, `%Error-UNDRIVEN` | Semantic / coding style | Fix RTL coding issue |
| `%Warning-WIDTH` becoming errors | Bit width mismatch | Check port and signal widths |
| Simulation exits non-zero with no parse errors | Functional failure / assertion | Go to Step 2 |
| `$fatal` or `ASSERTION FAILED` in stdout | Assertion failure | Extract failure time, go to Step 3 |

### Step 2 — Lint before diving into waveforms

Run `lint(file)` even if simulation already errored. Verible and Verilator lint often surface the root cause faster than reading waveforms.

If lint is clean, proceed to Step 3.

### Step 3 — Extract failure context and read the waveform

From the simulation stdout, find:
- The simulation time at failure (e.g., `$time`, assertion failure timestamp) — call it **T**
- Which signals or assertions were involved

If `run_simulation()` returned a `trace_vcd` path (the testbench had
`$dumpfile`/`$dumpvars`), inspect it directly — do **not** ask the user to open
a viewer:

1. `read_waveform(trace_vcd)` — discovery mode. Lists the available signal
   names and `end_time` so you use the exact hierarchical names the trace holds.
2. `read_waveform(trace_vcd, signals=[...], time_start=T-window, time_end=T+window)`
   — read the signals implicated by the failure across a tight window around T.
   Include the clock, reset, the state register, and any signal named in the
   assertion. The value just before the window is always included, so the state
   entering the window is known.

Reading the actual values at T usually distinguishes the competing hypotheses
before you ever open the RTL — e.g. a counter that is one tick behind, a state
machine stuck in a state, or an X propagating from an unreset register.

`read_waveform` accepts `.fst` traces too (converted automatically); `.fsdb`
does not parse — re-run with a `$dumpfile` VCD if that is all you have.

### Step 4 — Read the RTL

Call `read_rtl()` on the module(s) implicated by the error. Focus on:
- The specific line numbers from the error list
- The always block containing the failing logic
- Reset conditions for involved signals

### Step 5 — Form ranked hypotheses

Generate 2–3 hypotheses, most likely first. For each:
- State what you believe is wrong
- Identify the RTL line that would be the fix
- Estimate confidence (high / medium / low)

### Step 6 — Propose and dry-run the fix

Call `write_rtl(file, new_content, dry_run=True)` targeting the top hypothesis. Review the diff:
- Is the change minimal and targeted?
- Does it address the hypothesis cleanly without side effects?

### Step 7 — Verify

Call `run_simulation()` again with the same arguments. If it passes, the fix is confirmed. If it still fails, re-rank hypotheses and iterate from Step 4 for the next candidate.

### Step 8 — Write a root cause summary

After a successful fix, summarize:
- Confirmed root cause (one sentence)
- Evidence chain (what the error output showed → what the RTL had wrong)
- Fix applied (the key line change)
- Verification (simulation now passes)

---

## Few-Shot Examples

### Example 1 — Blocking assignment in sequential always block

**Context**: UART TX module simulation fails immediately at compile time.

**`run_simulation()` output:**
```json
{
  "exit_code": 1,
  "errors": [
    {
      "file": "examples/uart/uart_tx.sv",
      "line": 52,
      "severity": "error",
      "message": "Blocking assignment to non-blocking assignment context in: 'baud_cnt' [-Wblocking]"
    }
  ],
  "warnings": [],
  "raw_stderr": "%Error: examples/uart/uart_tx.sv:52:21: Blocking assignment to non-blocking assignment context in: 'baud_cnt' [-Wblocking]\n%Error: Exiting due to 1 error(s)"
}
```

**Correct reasoning**:

1. `%Error` with `-Wblocking` — this is a semantic coding error: blocking assignment (`=`) inside an `always_ff` block. Verilator is strict about this; other simulators may silently allow it.
2. Call `read_rtl("examples/uart/uart_tx.sv", start_line=45, end_line=60)` to see the context.
3. Hypothesis (high confidence): Line 52 uses `=` instead of `<=` inside an `always_ff`. This is almost always the entire bug.
4. Fix: Change `baud_cnt = baud_cnt + 1;` to `baud_cnt <= baud_cnt + 1;` (and any other blocking assignments in the same block).

**`read_rtl()` output (line 52 region)**:
```
  48    always_ff @(posedge clk or negedge rst_n) begin
  49        if (!rst_n) begin
  50            baud_cnt <= '0;
  51        end else if (state == START) begin
  52            baud_cnt = baud_cnt + 1;   // <-- blocking assignment — BUG
  53        end
  54    end
```

**Fix applied** (`write_rtl(dry_run=True)` diff):
```diff
-            baud_cnt = baud_cnt + 1;
+            baud_cnt <= baud_cnt + 1;
```

**Verification**: Re-run `run_simulation()` → `exit_code: 0`.

---

### Example 2 — Off-by-one in baud rate counter comparison

**Context**: UART TX simulation compiles cleanly but the testbench reports a framing error. The byte sent takes longer than expected and the stop bit overlaps with the next start bit.

**`run_simulation()` output:**
```json
{
  "exit_code": 1,
  "errors": [
    {
      "file": "examples/uart/uart_tx_tb.sv",
      "line": 78,
      "severity": "error",
      "message": "ASSERTION FAILED: framing error detected at time 4523480ns"
    }
  ],
  "warnings": [],
  "raw_stdout": "[TB] Sending 0xA5\n[TB] FRAMING ERROR at bit 7: expected HIGH stop bit, got LOW at time 4523480ns\n[TB] FAIL"
}
```

**Correct reasoning**:

1. Simulation compiled — this is a functional bug, not a coding style issue.
2. Failure: framing error at bit 7. The stop bit is low when it should be high. This means the data phase is running one cycle too long, pushing the TX line low during what the receiver thinks is the stop bit.
3. Hypothesis 1 (high confidence): Off-by-one in the baud counter comparison. If the check is `baud_cnt == CLKS_PER_BIT` instead of `baud_cnt == CLKS_PER_BIT - 1`, each bit period is one clock cycle too long. After 8 data bits, the accumulated error shifts the stop bit out of the valid window.
4. Hypothesis 2 (medium confidence): Wrong number of bits transmitted (bit_idx check at 3'd6 instead of 3'd7).

Call `read_rtl("examples/uart/uart_tx.sv")` and look for the baud counter comparison.

**`read_rtl()` relevant excerpt**:
```
  38    localparam int CLKS_PER_BIT = CLK_FREQ / BAUD_RATE;
  ...
  61            DATA: begin
  62                tx <= shift_reg[0];
  63                if (baud_cnt == CLKS_PER_BIT) begin   // <-- off-by-one BUG
  64                    baud_cnt  <= '0;
  65                    shift_reg <= {1'b0, shift_reg[7:1]};
  66                    if (bit_idx == 3'd7) begin
  67                        state <= STOP;
  68                    end else begin
  69                        bit_idx <= bit_idx + 1;
  70                    end
  71                end else begin
  72                    baud_cnt <= baud_cnt + 1;
  73                end
  74            end
```

**Analysis**: The counter starts at 0 and increments. If `CLKS_PER_BIT = 434` (50 MHz / 115200), the correct window is 0–433 (434 cycles). Comparing `== CLKS_PER_BIT` (434) means the counter runs 0–434 = **435 cycles per bit** — one extra cycle per bit, eight extra cycles across the DATA phase, pushing the stop bit start one bit period late.

**Fix** (`write_rtl(dry_run=True)` diff):
```diff
-                if (baud_cnt == CLKS_PER_BIT) begin
+                if (baud_cnt == CLKS_PER_BIT - 1) begin
```

Apply the same fix to START and STOP state comparisons if they have the same bug.

**Verification**: Re-run `run_simulation()` → `exit_code: 0`, `[TB] PASS`.

---

### Example 3 — Reading the waveform to localize a functional bug

**Context**: An FSM-driven arbiter compiles and runs, but the testbench reports
the wrong grant at time 2450. No assertion names the cause.

**`run_simulation()` output:**
```json
{
  "exit_code": 1,
  "trace_vcd": "/tmp/silica_trace_ab12/dump.vcd",
  "errors": [
    {"file": "arbiter_tb.sv", "line": 61, "severity": "error",
     "message": "ASSERTION FAILED: expected grant=01, got grant=00 at time 2450ns"}
  ],
  "raw_stdout": "[TB] req=11 at 2400ns\n[TB] MISMATCH at 2450ns: grant=00\n[TB] FAIL"
}
```

**Correct reasoning**:

1. Functional failure at **T = 2450**, involving `grant` and `req`. A `trace_vcd`
   is present — read it instead of guessing.
2. `read_waveform("/tmp/silica_trace_ab12/dump.vcd")` → discover the names:
   `arbiter_tb.dut.state`, `.grant`, `.req`, `.clk`, `.rst_n`.
3. `read_waveform(trace_vcd, signals=["dut.state", "dut.req", "dut.grant", "dut.clk"], time_start=2350, time_end=2470)`:

```json
{"signals": [
  {"name": "arbiter_tb.dut.state", "transitions": [
     {"time": 2350, "value": "01"}, {"time": 2410, "value": "11"}]},
  {"name": "arbiter_tb.dut.grant", "transitions": [
     {"time": 2350, "value": "10"}, {"time": 2410, "value": "00"}]},
  {"name": "arbiter_tb.dut.req",  "transitions": [
     {"time": 2350, "value": "10"}, {"time": 2400, "value": "11"}]}
]}
```

4. **Reading the values**: `state` entered `11` (an unlisted/default encoding)
   right when `req` went to `11`, and `grant` collapsed to `00`. The FSM has no
   case arm for `state == 2'b11`, so it falls through to a default that drives
   `grant = 0`. This is a missing `default:`/incomplete case — not an off-by-one.
5. Hypothesis (high confidence): the arbiter's `case (state)` lacks the
   both-requesting arm. Confirm with `read_rtl()` on the FSM's `always_comb`.

**Fix**: add the missing case arm (or a `default:` that holds the last grant).

**Verification**: Re-run `run_simulation()` → `exit_code: 0`, and
`read_waveform(...)` now shows `grant=01` at 2450.

---

## Edge Cases

- **X-propagation from uninitialized signals**: If the simulation produces `x` values that propagate through logic, check reset initialization. Every register needs a reset value. Verilator X-propagation (`--x-assign unique`) is stricter than commercial simulators.
- **Timescale mismatches**: `%Warning-TIMESCALEMOD` from Verilator when files have inconsistent `timescale` directives. Add `-Wno-TIMESCALEMOD` flag or add matching timescale to all files.
- **Testbench-only vs. synthesizable**: Errors in `$display`, `$dumpfile`, `initial` blocks are testbench-only constructs and will error in synthesis. Do not attempt to `synthesize()` a testbench file.
- **Width mismatches that don't error but produce wrong behavior**: `%Warning-WIDTH` treated as a warning can hide real bugs. If simulation produces wrong values on arithmetic operations, check for implicit truncation.
