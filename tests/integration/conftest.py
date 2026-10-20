"""RTL fixtures shared across integration tests."""

import subprocess

import pytest

from silica import oss_cad_suite

# ---------------------------------------------------------------------------
# RTL fixtures — simple self-contained designs written to tmp_path
# ---------------------------------------------------------------------------

COUNTER_V = """\
`timescale 1ns/1ps
module counter (
    input  wire       clk,
    input  wire       rst,
    output reg  [3:0] count
);
    always @(posedge clk or posedge rst) begin
        if (rst) count <= 4'b0;
        else     count <= count + 4'b1;
    end
endmodule
"""

COUNTER_TB_V = """\
`timescale 1ns/1ps
module counter_tb;
    reg clk = 0;
    reg rst = 1;
    wire [3:0] count;

    counter dut (.clk(clk), .rst(rst), .count(count));

    always #5 clk = ~clk;

    initial begin
        repeat (3) @(posedge clk);
        rst = 0;
        repeat (20) @(posedge clk);
        $display("PASS count=%0d", count);
        $finish;
    end
endmodule
"""

COUNTER_BAD_V = """\
`timescale 1ns/1ps
module counter_bad (
    input wire clk
    // Missing closing parenthesis + body — deliberate syntax error
"""

COUNTER_FORMAL_V = """\
`timescale 1ns/1ps
module counter_formal (
    input  wire       clk,
    input  wire       rst,
    output reg  [3:0] count
);
    always @(posedge clk or posedge rst) begin
        if (rst) count <= 4'b0;
        else     count <= count + 4'b1;
    end

`ifdef FORMAL
    // A 4-bit counter can never exceed 0xF — trivially true, must PASS
    always @(posedge clk) begin
        if (!rst)
            assert (count <= 4'hf);
    end
`endif
endmodule
"""

COUNTER_FAIL_V = """\
`timescale 1ns/1ps
module counter_fail (
    input  wire       clk,
    input  wire       rst,
    output reg  [3:0] count
);
    always @(posedge clk or posedge rst) begin
        if (rst) count <= 4'b0;
        else     count <= count + 4'b1;
    end

`ifdef FORMAL
    // count < 3 will FAIL after 3 clock cycles
    always @(posedge clk) begin
        if (!rst)
            assert (count < 4'd3);
    end
`endif
endmodule
"""

COUNTER_VHD = """\
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity counter is
    port (
        clk   : in  std_logic;
        rst   : in  std_logic;
        count : out std_logic_vector(3 downto 0)
    );
end entity counter;

architecture rtl of counter is
    signal cnt : unsigned(3 downto 0) := (others => '0');
begin
    process(clk, rst)
    begin
        if rst = '1' then
            cnt <= (others => '0');
        elsif rising_edge(clk) then
            cnt <= cnt + 1;
        end if;
    end process;
    count <= std_logic_vector(cnt);
end architecture rtl;
"""

COUNTER_TB_VHD = """\
library ieee;
use ieee.std_logic_1164.all;

entity counter_tb is
end entity counter_tb;

architecture bench of counter_tb is
    signal clk   : std_logic := '0';
    signal rst   : std_logic := '1';
    signal count : std_logic_vector(3 downto 0);
begin
    dut: entity work.counter
        port map (clk => clk, rst => rst, count => count);

    clk <= not clk after 5 ns;

    stim: process
    begin
        wait for 15 ns;
        rst <= '0';
        wait;
    end process;
end architecture bench;
"""


@pytest.fixture
def counter_v(tmp_path):
    f = tmp_path / "counter.v"
    f.write_text(COUNTER_V)
    return str(f)


@pytest.fixture
def counter_tb_v(tmp_path):
    f = tmp_path / "counter_tb.v"
    f.write_text(COUNTER_TB_V)
    return str(f)


@pytest.fixture
def counter_bad_v(tmp_path):
    f = tmp_path / "counter_bad.v"
    f.write_text(COUNTER_BAD_V)
    return str(f)


@pytest.fixture
def counter_formal_v(tmp_path):
    f = tmp_path / "counter_formal.v"
    f.write_text(COUNTER_FORMAL_V)
    return str(f)


@pytest.fixture
def counter_fail_v(tmp_path):
    f = tmp_path / "counter_fail.v"
    f.write_text(COUNTER_FAIL_V)
    return str(f)


@pytest.fixture
def counter_vhd(tmp_path):
    f = tmp_path / "counter.vhd"
    f.write_text(COUNTER_VHD)
    return str(f)


@pytest.fixture
def counter_tb_vhd(tmp_path):
    f = tmp_path / "counter_tb.vhd"
    f.write_text(COUNTER_TB_VHD)
    return str(f)


@pytest.fixture
def ice40_netlist(tmp_path, counter_v):
    """Synthesize counter.v to an iCE40 JSON netlist using yosys directly."""
    yosys_bin = oss_cad_suite.which("yosys")
    if not yosys_bin:
        pytest.skip("yosys not found — cannot build ice40 netlist fixture")
    json_out = tmp_path / "counter_ice40.json"
    script = f'read_verilog "{counter_v}"; synth_ice40 -top counter -json "{json_out}"'
    cp = subprocess.run(
        [yosys_bin, "-p", script],
        capture_output=True,
        text=True,
        env=oss_cad_suite.env_with_suite(),
    )
    if cp.returncode != 0 or not json_out.exists():
        pytest.skip(f"yosys ice40 synthesis failed:\n{cp.stderr}")
    return str(json_out)


@pytest.fixture
def ecp5_netlist(tmp_path, counter_v):
    """Synthesize counter.v to an ECP5 JSON netlist using yosys directly."""
    yosys_bin = oss_cad_suite.which("yosys")
    if not yosys_bin:
        pytest.skip("yosys not found — cannot build ecp5 netlist fixture")
    json_out = tmp_path / "counter_ecp5.json"
    script = f'read_verilog "{counter_v}"; synth_ecp5 -top counter -json "{json_out}"'
    cp = subprocess.run(
        [yosys_bin, "-p", script],
        capture_output=True,
        text=True,
        env=oss_cad_suite.env_with_suite(),
    )
    if cp.returncode != 0 or not json_out.exists():
        pytest.skip(f"yosys ecp5 synthesis failed:\n{cp.stderr}")
    return str(json_out)


COUNTER_INEQUIV_V = """\
`timescale 1ns/1ps
module counter (
    input  wire       clk,
    input  wire       rst,
    output reg  [3:0] count
);
    // counts down — inequivalent to counter which counts up
    always @(posedge clk or posedge rst) begin
        if (rst) count <= 4'b0;
        else     count <= count - 4'b1;
    end
endmodule
"""


@pytest.fixture
def counter_inequiv_v(tmp_path):
    f = tmp_path / "counter_inequiv.v"
    f.write_text(COUNTER_INEQUIV_V)
    return str(f)
