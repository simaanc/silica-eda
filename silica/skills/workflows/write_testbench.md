# Skill: Write Testbench

**Task**: Generate a complete, self-checking testbench for an RTL module — one that exercises real behavior and reports PASS/FAIL unambiguously.

**When to use**: The user asks for a testbench, asks to "verify" or "test" a module and none exists, or an existing testbench is stimulus-only (drives inputs but never checks outputs).

---

## Reasoning Script

Follow these steps in order. Never emit a testbench without a self-checking mechanism.

### Step 1 — Read and understand the DUT

Call `read_rtl(file)` on the module under test. Extract:
- The full port list: direction, width, and clock/reset signals
- Parameters and their defaults (`CLK_FREQ`, `WIDTH`, `DEPTH`, ...)
- The handshake or protocol on each interface (valid/ready, req/ack, strobe, raw combinational)
- Reset polarity and synchronicity (`rst_n` async-low vs `rst` sync-high)

If the module instantiates submodules you don't recognize, call `get_project_structure()` and `read_rtl()` on them — testbench timing often depends on internal latency.

### Step 2 — Decide the verification strategy

Pick the simplest strategy that actually checks correctness:

| DUT type | Strategy |
|---|---|
| Combinational (ALU, decoder, mux) | Exhaustive or constrained-random input sweep + golden model in the TB |
| Simple sequential (counter, shift reg) | Directed sequences + cycle-accurate expected-value model |
| Protocol block (UART, SPI, AXI-lite) | Drive one side, implement the *counterpart* protocol in the TB (e.g., a bit-banged receiver checks a transmitter) |
| FIFO / memory | Scoreboard: push expected values into a queue on write, pop and compare on read |
| FSM controller | Directed sequences per documented transition + a coverage checklist in comments |

### Step 3 — Build the testbench skeleton

Every generated testbench must contain, in this order:

1. `timescale` directive matching the DUT (or `1ns/1ps` default)
2. Clock generation (`always #(PERIOD/2) clk = ~clk;`) — derive PERIOD from DUT parameters when they imply one
3. Reset sequence: assert reset for several cycles, deassert synchronously
4. DUT instantiation with **named** port connections — never positional
5. Stimulus (directed tasks or loops)
6. **Checking**: comparisons against expected values, `$error`/`$fatal` on mismatch
7. Pass/fail bookkeeping: an error counter, and a final block printing exactly `PASS` or `FAIL` before `$finish`
8. Waveform dump guarded so it can be enabled: `$dumpfile("tb.vcd"); $dumpvars(0, tb);`
9. A watchdog: `initial begin #SIM_TIMEOUT; $display("TIMEOUT"); $fatal; end` so a hung handshake fails instead of hanging the simulator

### Step 4 — Write stimulus as reusable tasks

Wrap each transaction in a task (`send_byte`, `axi_write`, `push`, `pop`). Directed cases first (reset value, single transaction, back-to-back, boundary values like all-zeros/all-ones/MSB set), then randomized ones if the interface allows.

### Step 5 — Dry-run and iterate

1. `write_rtl(tb_file, content, dry_run=True)` — review the diff
2. After confirmation, write it and call `run_simulation(file=dut, testbench=tb_file)`
3. Compile errors → fix and re-run. A testbench that never ran is not delivered.
4. Confirm the output actually contains the `PASS` line — exit code 0 with no checks executed is a silent false positive.

### Step 6 — Sanity-check the checker

Temporarily break one expected value (or recommend the user do so) and confirm the TB reports FAIL. A self-checking bench that can't fail is worse than none.

---

## Few-Shot Examples

### Example 1 — UART transmitter (protocol counterpart strategy)

**Context**: `examples/uart/uart_tx.sv`, ports `clk, rst_n, tx_start, tx_data[7:0], tx, tx_busy`, parameters `CLK_FREQ=50_000_000, BAUD_RATE=115200`.

**Reasoning**: The TB must act as a UART *receiver*: wait for the start bit, sample each bit at the bit-period midpoint, reassemble the byte, check the stop bit. Sampling mid-bit makes the check robust to one-cycle edge placement.

**Key testbench fragment**:
```systemverilog
localparam int CLKS_PER_BIT = CLK_FREQ / BAUD_RATE;

task automatic recv_byte(output logic [7:0] data);
    @(negedge tx);                       // start bit edge
    repeat (CLKS_PER_BIT / 2) @(posedge clk);
    if (tx !== 1'b0) begin errors++; $error("start bit not low"); end
    for (int i = 0; i < 8; i++) begin
        repeat (CLKS_PER_BIT) @(posedge clk);
        data[i] = tx;                    // LSB first
    end
    repeat (CLKS_PER_BIT) @(posedge clk);
    if (tx !== 1'b1) begin errors++; $error("framing: stop bit low"); end
endtask

initial begin
    logic [7:0] rx;
    reset_dut();
    foreach (test_bytes[i]) begin
        fork
            begin tx_data = test_bytes[i]; tx_start = 1; @(posedge clk); tx_start = 0; end
            recv_byte(rx);
        join
        if (rx !== test_bytes[i]) begin errors++; $error("sent %h got %h", test_bytes[i], rx); end
        wait (!tx_busy);
    end
    if (errors == 0) $display("PASS"); else $display("FAIL: %0d errors", errors);
    $finish;
end
```

**Verification**: `run_simulation(file="examples/uart/uart_tx.sv", testbench="examples/uart/uart_tx_tb.sv")` → `exit_code: 0`, stdout contains `PASS`.

### Example 2 — Synchronous FIFO (scoreboard strategy)

**Context**: `fifo.sv`, ports `clk, rst_n, wr_en, wr_data[15:0], full, rd_en, rd_data[15:0], empty`, parameter `DEPTH=16`.

**Reasoning**: Order-preserving storage → a SystemVerilog queue is the golden model. Push on accepted write, pop-and-compare on accepted read. Must cover the classic corner cases: fill to full, drain to empty, simultaneous read+write, write-when-full ignored.

**Key testbench fragment**:
```systemverilog
logic [15:0] model_q [$];

always @(posedge clk) if (rst_n) begin
    if (wr_en && !full)  model_q.push_back(wr_data);
    if (rd_en && !empty) begin
        automatic logic [15:0] expected = model_q.pop_front();
        if (rd_data !== expected) begin
            errors++;
            $error("FIFO order: expected %h got %h", expected, rd_data);
        end
    end
end
```

Directed sequence: fill DEPTH+2 writes (last two must be blocked by `full`), drain fully (check `empty`), then 500 randomized interleaved read/write cycles. Final check: `model_q.size() == 0` after full drain.

**Result**: `exit_code: 0`, `PASS`, and re-running with a deliberately corrupted expected value reports FAIL — checker confirmed live.

---

## Edge Cases

- **`$dumpvars` on large memories**: dumping a deep RAM makes VCDs enormous — dump depth 1–2 (`$dumpvars(1, tb)`) or exclude the memory instance.
- **Clock-domain crossings**: if the DUT has two clocks, generate both with non-integer-ratio periods (e.g., 10ns and 7ns) or CDC bugs will hide behind aligned edges.
- **VHDL DUTs**: GHDL infers the top entity from the testbench file name — keep entity name and file name consistent, and use `run_simulation(..., simulator="ghdl")`.
- **`x` at time zero**: initialize TB-driven signals in declarations (`logic tx_start = 0;`); undriven inputs during reset propagate `x` and produce false mismatches with `!==`.
- **Always compare with `!==`/`===`**: `!=` treats `x` as "maybe equal" and silently passes broken tests.
