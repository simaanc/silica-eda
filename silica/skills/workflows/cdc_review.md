# Skill: CDC Review

**Task**: Find every clock domain crossing in a design, classify each against known-safe synchronization patterns, and report the unsafe ones with concrete fixes.

**When to use**: The design has more than one clock; before tape-out/bitstream sign-off; after adding an interface on a new clock (PCIe/USB/UART/video pixel clock); or when a design shows rare, non-reproducible corruption — the classic CDC symptom.

**Critical mindset**: RTL simulation is nearly useless for CDC. Simulators apply both edges in zero time and never model metastability, so a design with a broken crossing simulates clean and fails on silicon. This review is *structural* — trust the code, not the testbench.

---

## Reasoning Script

### Step 1 — Enumerate the clock domains

1. `get_project_structure()` — get the RTL file list.
2. `search_rtl("posedge")` — every distinct clock signal in sequential blocks is a domain. Group aliases (`clk_sys` passed down as `clk`) by following port connections with `read_rtl` on the instantiation sites.
3. `get_constraints()` — `create_clock` / `create_generated_clock` lines confirm the domain list and give frequencies. Derived clocks from the same PLL that are synchronous to each other are one domain for CDC purposes; note them.

One clock → no CDC, stop. Otherwise list domains: name, source, frequency.

### Step 2 — Find the crossings

For each register written in domain A, flag reads in domain B:

1. `search_rtl("<signal>")` for signals that appear near both `posedge clkA` and `posedge clkB` blocks.
2. Prioritize module boundaries: FIFOs, register files, handshake blocks, anything named `sync`, `cdc`, `async`, `resample`.
3. Resets count too: an async reset released in one domain but used in another is a crossing (reset de-assertion must be synchronized per-domain).

Build a crossing list: `{signal(s), from_domain, to_domain, width, file:line}`.

### Step 3 — Classify each crossing

| Crossing type | Safe pattern | Broken pattern (flag it) |
|---|---|---|
| Single-bit level/control | 2-flop (or 3-flop) synchronizer | Raw flop, or combinational logic **between** the domains before the first sync flop |
| Single-cycle pulse, fast→slow | Toggle synchronizer (XOR recovery) | 2-flop sync on the pulse itself — a 1-cycle pulse from a fast domain is swallowed |
| Multi-bit data bus | Handshake (req/ack) with stable data, or async FIFO | Per-bit 2-flop sync on the bus — bits arrive in different cycles (coherency loss) |
| Counter/pointer crossing (FIFO) | Gray-coded pointer + 2-flop sync | Binary pointer synced per-bit — multiple bits change per increment |
| Async reset distribution | Reset synchronizer per domain (async assert, sync de-assert) | Raw async reset consumed in a foreign domain |
| Quasi-static config (written once, then stable) | 2-flop sync + software-guaranteed stability, documented | Assumed-static signal that actually changes at runtime |

For each crossing, `read_rtl` the receiving side and check:

- First receiving flop is clocked by the destination clock, with **no logic** between the domain boundary and that flop.
- Nothing else consumes the signal before the second sync stage (`search_rtl` the intermediate `_meta`/`_ff1` net — it must have exactly one reader).
- Multi-bit: identify what guarantees the bus is stable while sampled (handshake state, gray coding, FIFO full/empty logic).

### Step 4 — Mechanical checks

- `lint(file)` on crossing modules — Verilator/Verible catch width and undriven issues in sync chains (e.g. only bit 0 of a bus actually synchronized).
- If SpyGlass is available (`lint(file, tool="spyglass")`), run it — it has true CDC rules.

### Step 5 — Verify the protocol, not the metastability

For handshake crossings, formal can prove the *protocol* even though it can't model metastability. Add assertions and `run_formal(mode="prove")`:

```systemverilog
// data must hold steady from req assertion until ack
assert property (@(posedge clk_src) req && !ack |=> $stable(data));
// req must not drop before ack
assert property (@(posedge clk_src) req && !ack |=> req);
```

For FIFO pointer crossings, assert gray-ness: `assert property (@(posedge wr_clk) $countones(wr_ptr_gray ^ $past(wr_ptr_gray)) <= 1);`

### Step 6 — Report

One row per crossing: signals, from→to, type, verdict (SAFE / UNSAFE / REVIEW), and for each UNSAFE a concrete fix. Never report "no issues" without listing the crossings examined — the value of the review is the enumeration.

---

## Few-Shot Examples

### Example 1 — Binary FIFO pointer crossed between domains

**Context**: Two clocks (`clk_wr` 100 MHz, `clk_rd` 25 MHz) with an async FIFO between them.

**`search_rtl("wr_ptr")` output:**
```json
{
  "matches": [
    {"file": "rtl/async_fifo.sv", "line": 31,
     "context": "always_ff @(posedge clk_wr) begin\n    if (push && !full)\n        wr_ptr <= wr_ptr + 1'b1;"},
    {"file": "rtl/async_fifo.sv", "line": 58,
     "context": "// bring write pointer into read domain\nalways_ff @(posedge clk_rd) begin\n    wr_ptr_meta <= wr_ptr;\n    wr_ptr_sync <= wr_ptr_meta;\nend"},
    {"file": "rtl/async_fifo.sv", "line": 64,
     "context": "assign empty = (rd_ptr == wr_ptr_sync);"}
  ],
  "match_count": 3,
  "truncated": false
}
```

**Correct reasoning**:

1. `wr_ptr` is written in `clk_wr` (line 31) and sampled in `clk_rd` (line 58) — a genuine crossing, and it has a 2-flop synchronizer. Looks safe at a glance.
2. But `wr_ptr` is a **binary counter**. On the increment `0111 → 1000`, all four bits change. Each bit's synchronizer resolves independently, so `wr_ptr_sync` can momentarily read **any** mix — e.g. `1111` — a pointer value that was never written.
3. Consequence: `empty` (line 64) deasserts early or glitches, and the read side pops garbage. This is the textbook async-FIFO bug, and no simulation will ever show it.
4. Verdict: **UNSAFE — multi-bit binary value through per-bit synchronizers.**

**Fix**: cross the pointer in gray code — exactly one bit changes per increment, so any sync outcome is either the old or the new value, both safe (conservative) for full/empty:

```systemverilog
// write domain: keep binary for addressing, cross the gray version
assign wr_ptr_gray_next = (wr_ptr_next >> 1) ^ wr_ptr_next;
always_ff @(posedge clk_wr) wr_ptr_gray <= wr_ptr_gray_next;

// read domain: synchronize the gray pointer
always_ff @(posedge clk_rd) begin
    wr_ptr_gray_meta <= wr_ptr_gray;
    wr_ptr_gray_sync <= wr_ptr_gray_meta;
end
assign empty = (rd_ptr_gray == wr_ptr_gray_sync);
```

Then verify structurally: `run_formal(mode="prove")` with `assert property (@(posedge clk_wr) $countones(wr_ptr_gray ^ $past(wr_ptr_gray)) <= 1);`

---

### Example 2 — Data bus with a synchronizer but no handshake

**Context**: Config register in `clk_cpu`, consumed by a UART divider in `clk_uart`.

**`read_rtl("rtl/uart_regs.sv", start_line=40, end_line=52)`:**
```
  40    // CPU writes the divider; UART side picks it up
  41    always_ff @(posedge clk_cpu)
  42        if (wr_en && addr == ADDR_DIV)
  43            divider <= wdata[15:0];
  44
  45    // synchronize into uart domain
  46    always_ff @(posedge clk_uart) begin
  47        divider_meta <= divider;
  48        divider_sync <= divider_meta;
  49    end
  50
  51    always_ff @(posedge clk_uart)
  52        baud_cnt_limit <= divider_sync;
```

**Correct reasoning**:

1. There *is* a 2-flop synchronizer (lines 46–49) — but on a **16-bit bus**. A write changing `0x000F → 0x0010` flips 5 bits; the UART domain can sample a torn value like `0x001F` and run at a garbage baud rate until the next resample.
2. Is it quasi-static? Software writes the divider at init, but nothing in hardware *guarantees* it: a runtime baud change would tear. Quasi-static is only SAFE if documented and enforced; here it's an accident.
3. Verdict: **UNSAFE (coherency) — REVIEW downgrade possible** only if the register is provably write-once.

**Fix** (handshake — data held stable while sampled):

```systemverilog
// clk_cpu side: toggle a request when the divider changes
always_ff @(posedge clk_cpu)
    if (wr_en && addr == ADDR_DIV) begin
        divider   <= wdata[15:0];
        div_req_t <= ~div_req_t;          // toggle, safe to sync
    end

// clk_uart side: sync the toggle, then sample the stable bus
always_ff @(posedge clk_uart) begin
    div_req_meta <= div_req_t;
    div_req_sync <= div_req_meta;
    div_req_d    <= div_req_sync;
    if (div_req_sync ^ div_req_d)          // one clean load per write
        baud_cnt_limit <= divider;         // divider stable since the toggle
end
```

The bus itself crosses unsynchronized — safe because it is sampled ≥2 destination clocks after its last change, guaranteed by the toggle protocol. Formal-check with `assert property (@(posedge clk_cpu) $changed(div_req_t) |-> $stable(divider) throughout ...)` style stability assertions.

---

## Edge Cases

- **Synchronous-but-related clocks**: derived clocks from one PLL (÷2, ÷4) with constrained phase are *not* CDC — treat crossings as same-domain timing paths, but say so explicitly in the report.
- **Sync flops must not be retimed**: the two sync stages need `(* ASYNC_REG = "TRUE" *)` (Xilinx) / `syn_preserve` attributes, or synthesis may merge/retime them and silently remove the protection. Check attributes during the review.
- **Handshake across a huge frequency ratio**: fast→slow pulse crossings need the toggle pattern; a 100:1 ratio with plain req/ack stretches transactions — flag throughput, not just safety.
- **Reset crossings hide in plain sight**: `search_rtl("rst")` in every domain; each domain needs its own reset synchronizer (async assert, sync de-assert). A single global async reset released near a clock edge causes some domains to leave reset a cycle apart.
- **CDC through memories**: dual-clock RAMs are safe for the *array* but not for anything derived from addresses across domains — the pointer logic is still a crossing.
- **Verdicts need evidence**: SAFE verdicts cite the pattern found (file:line of both sync flops); UNSAFE verdicts cite the receiving flop and the failure mode in one sentence.
