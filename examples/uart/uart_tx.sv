// uart_tx.sv — UART transmitter, 8N1, synchronous design
//
// Interface:
//   valid/ready handshake — assert valid with data_in; ready pulses high when
//   the transmitter accepts the byte and begins transmission.
//   tx idles HIGH; start bit is LOW.

`timescale 1ns/1ps

module uart_tx #(
    parameter int CLK_FREQ  = 50_000_000,  // Hz
    parameter int BAUD_RATE = 115_200       // bps
) (
    input  logic       clk,
    input  logic       rst_n,   // active-low async reset
    input  logic [7:0] data_in,
    input  logic       valid,
    output logic       ready,
    output logic       tx
);

    localparam int CLKS_PER_BIT = CLK_FREQ / BAUD_RATE;  // 434 @ 50 MHz / 115200

    typedef enum logic [1:0] {
        IDLE  = 2'b00,
        START = 2'b01,
        DATA  = 2'b10,
        STOP  = 2'b11
    } state_t;

    state_t        state;
    logic [15:0]   baud_cnt;
    logic [2:0]    bit_idx;
    logic [7:0]    shift_reg;

    assign ready = (state == IDLE);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            baud_cnt  <= '0;
            bit_idx   <= '0;
            shift_reg <= '0;
            tx        <= 1'b1;
        end else begin
            case (state)
                IDLE: begin
                    tx <= 1'b1;
                    if (valid) begin
                        state     <= START;
                        shift_reg <= data_in;
                        baud_cnt  <= '0;
                    end
                end

                START: begin
                    tx <= 1'b0;
                    if (baud_cnt == CLKS_PER_BIT - 1) begin
                        state    <= DATA;
                        baud_cnt <= '0;
                        bit_idx  <= '0;
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                DATA: begin
                    tx <= shift_reg[0];
                    if (baud_cnt == CLKS_PER_BIT - 1) begin
                        baud_cnt  <= '0;
                        shift_reg <= {1'b0, shift_reg[7:1]};
                        if (bit_idx == 3'd7) begin
                            state <= STOP;
                        end else begin
                            bit_idx <= bit_idx + 1;
                        end
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                STOP: begin
                    tx <= 1'b1;
                    if (baud_cnt == CLKS_PER_BIT - 1) begin
                        state    <= IDLE;
                        baud_cnt <= '0;
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
