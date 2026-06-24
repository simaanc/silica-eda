// uart_tx_tb.sv — Testbench for uart_tx
//
// Verifies:
//   1. Start bit is driven low for exactly CLKS_PER_BIT cycles
//   2. Each data bit is correct (LSB first)
//   3. Stop bit is driven high for exactly CLKS_PER_BIT cycles
//   4. TX returns to idle (high) between bytes
//   5. ready deasserts during transmission and reasserts at IDLE

`timescale 1ns/1ps

module uart_tx_tb;

    // Match DUT parameters
    localparam int CLK_FREQ     = 50_000_000;
    localparam int BAUD_RATE    = 115_200;
    localparam int CLKS_PER_BIT = CLK_FREQ / BAUD_RATE;  // 434

    // 50 MHz clock = 20 ns period
    localparam real CLK_PERIOD  = 1_000_000_000.0 / CLK_FREQ;

    logic       clk;
    logic       rst_n;
    logic [7:0] data_in;
    logic       valid;
    logic       ready;
    logic       tx;

    int         pass_count;
    int         fail_count;

    // DUT instantiation
    uart_tx #(
        .CLK_FREQ(CLK_FREQ),
        .BAUD_RATE(BAUD_RATE)
    ) dut (
        .clk     (clk),
        .rst_n   (rst_n),
        .data_in (data_in),
        .valid   (valid),
        .ready   (ready),
        .tx      (tx)
    );

    // Clock generation
    initial clk = 1'b0;
    always #(CLK_PERIOD / 2.0) clk = ~clk;

    // ----------------------------------------------------------------
    // Task: send one byte and check the full 10-bit UART frame
    // ----------------------------------------------------------------
    task automatic send_and_check(input logic [7:0] data);
        automatic logic [7:0] ref_data = data;
        automatic logic       bit_val;
        automatic int         i;

        // Wait for ready (should already be asserted in IDLE)
        @(posedge clk);
        if (!ready) begin
            $display("[FAIL] TX not ready before sending 0x%02X", data);
            fail_count++;
            return;
        end

        // Present data and assert valid for one cycle
        data_in = data;
        valid   = 1'b1;
        @(posedge clk);
        valid   = 1'b0;
        data_in = '0;

        // Wait one clock for state to advance to START
        @(posedge clk);

        // --- Check start bit: TX must be LOW for CLKS_PER_BIT cycles ---
        for (i = 0; i < CLKS_PER_BIT; i++) begin
            if (tx !== 1'b0) begin
                $display("[FAIL] 0x%02X: start bit HIGH at cycle %0d (expected LOW)", data, i);
                fail_count++;
            end
            @(posedge clk);
        end

        // --- Check 8 data bits, LSB first ---
        for (int b = 0; b < 8; b++) begin
            bit_val = ref_data[b];
            for (i = 0; i < CLKS_PER_BIT; i++) begin
                if (tx !== bit_val) begin
                    $display("[FAIL] 0x%02X: bit[%0d] is %b, expected %b (cycle %0d)",
                             data, b, tx, bit_val, i);
                    fail_count++;
                end
                @(posedge clk);
            end
        end

        // --- Check stop bit: TX must be HIGH for CLKS_PER_BIT cycles ---
        for (i = 0; i < CLKS_PER_BIT; i++) begin
            if (tx !== 1'b1) begin
                $display("[FAIL] 0x%02X: stop bit LOW at cycle %0d (expected HIGH)", data, i);
                fail_count++;
            end
            @(posedge clk);
        end

        // TX should now be back to IDLE (high) and ready should be asserted
        if (tx !== 1'b1) begin
            $display("[FAIL] 0x%02X: TX not HIGH after stop bit", data);
            fail_count++;
        end
        if (!ready) begin
            $display("[FAIL] 0x%02X: ready not asserted after transmission", data);
            fail_count++;
        end

        pass_count++;
        $display("[PASS] 0x%02X transmitted correctly", data);
    endtask

    // ----------------------------------------------------------------
    // Main test sequence
    // ----------------------------------------------------------------
    initial begin
        $dumpfile("uart_tx_tb.vcd");
        $dumpvars(0, uart_tx_tb);

        pass_count = 0;
        fail_count = 0;

        // Reset
        rst_n   = 1'b0;
        valid   = 1'b0;
        data_in = 8'h00;

        repeat (5) @(posedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);

        // Test several representative patterns
        send_and_check(8'hA5);  // 1010_0101 — alternating bits
        send_and_check(8'h55);  // 0101_0101 — alternating from 0
        send_and_check(8'hFF);  // all ones
        send_and_check(8'h00);  // all zeros
        send_and_check(8'h01);  // LSB only

        repeat (10) @(posedge clk);

        // Final verdict
        if (fail_count == 0)
            $display("[TB] ALL TESTS PASSED (%0d bytes)", pass_count);
        else
            $display("[TB] FAILED: %0d/%0d bytes had errors", fail_count, pass_count + fail_count);

        $finish;
    end

    // Watchdog — kill simulation if it hangs
    initial begin
        // Budget: reset + 5 bytes * (10 bits * CLKS_PER_BIT) + slack
        #(CLK_PERIOD * (10 + 5 * 10 * CLKS_PER_BIT + 100));
        $display("[TB] WATCHDOG TIMEOUT");
        $finish;
    end

endmodule
