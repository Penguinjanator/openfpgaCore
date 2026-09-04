//------------------------------------------------------------------------------
// tb_settle_probe — additive A/BA command-setup observability bench
// (2026-08 DE10 dual-chip 128MB module address-margin work).
//
// io_sdram (test copy == targets/mister/io_sdram.v, split DQ) wired straight
// to sdram_model_full.  The C++ harness (tb_settle_probe_main.cpp) pulses the
// word interface directly — no slave/arbiter in between — and reads the
// model's settle-checker counters (chk_cmd_total / chk_cmd_setup0 /
// chk_min_setup / chk_last_setup) plus `errors` via --public-flat-rw.
//
// Expected on the Stage-A (early-address-drive) controller, BANK_ROW_TRACK=1,
// no masked burst-write beats driven: chk_cmd_setup0 == 0, chk_min_setup >= 1.
// No production RTL is touched; bench-only file.
//------------------------------------------------------------------------------

module tb_settle_probe (
    input  wire        clk,
    input  wire        reset_n,

    // io_sdram word interface, driven by the harness (1-cycle pulses)
    input  wire        word_rd,
    input  wire        word_wr,
    input  wire [23:0] word_addr,
    input  wire [31:0] word_data,
    input  wire [3:0]  word_wstrb,
    input  wire [3:0]  word_burst_len,     // 0=single, N=N+1 words (read)
    output wire [31:0] word_q,
    output wire        word_busy,
    output wire        word_q_valid,
    output wire        word_wr_done,

    // scanout-style burst read injection
    input  wire        burst_rd,
    input  wire [24:0] burst_addr,          // HALFWORD address
    input  wire [10:0] burst_len,           // 32-bit words (burst_32bit=1)
    output wire        burst_data_valid,
    output wire        burst_data_done,

    output wire [31:0] model_errors,
    output wire [5:0]  ctrl_state
);

wire        phy_cke, phy_clk, phy_cas, phy_ras, phy_we, phy_ncs;
wire [1:0]  phy_ba, phy_dqm;
wire [12:0] phy_a;
wire [15:0] ctrl_dq_out, model_dq_out;
wire        ctrl_dq_oe, model_dq_oe;
wire [15:0] dq_to_ctrl = model_dq_oe ? model_dq_out : 16'h0;

// DUT: MiSTer controller (test variant with split DQ)
io_sdram sdram_ctrl (
    .controller_clk(clk), .chip_clk(clk), .clk_90(clk), .reset_n(reset_n),
    .phy_cke(phy_cke), .phy_clk(phy_clk),
    .phy_cas(phy_cas), .phy_ras(phy_ras), .phy_we(phy_we),
    .phy_ba(phy_ba), .phy_a(phy_a),
    .phy_dq_in(dq_to_ctrl),
    .phy_dq_out_port(ctrl_dq_out), .phy_dq_oe_port(ctrl_dq_oe),
    .phy_dqm(phy_dqm), .phy_ncs(phy_ncs),
    .burst_rd(burst_rd), .burst_addr(burst_addr), .burst_len(burst_len),
    .burst_32bit(1'b1),
    .burst_data(), .burst_data_valid(burst_data_valid),
    .burst_data_done(burst_data_done),
    .burstwr(1'b0), .burstwr_addr(25'b0), .burstwr_ready(),
    .burstwr_strobe(1'b0), .burstwr_data(16'b0), .burstwr_done(1'b0),
    .word_rd(word_rd), .word_wr(word_wr),
    .word_addr(word_addr), .word_data(word_data), .word_wstrb(word_wstrb),
    .word_data_next(32'b0), .word_wstrb_next(4'b0),
    .word_burst_len(word_burst_len), .word_burst_wr_len(4'd0),
    .word_q(word_q), .word_busy(word_busy), .word_q_valid(word_q_valid),
    .word_wr_data_next(), .word_wr_done(word_wr_done),
    .burst_wr_direct_data(32'b0), .burst_wr_direct_strb(4'b0),
    .dbg_io()
);

// Ground truth chip model with the settle checker
sdram_model_full sdram_chip (
    .clk(phy_clk), .cke(phy_cke), .cs_n(phy_ncs),
    .ras_n(phy_ras), .cas_n(phy_cas), .we_n(phy_we),
    .ba(phy_ba), .a(phy_a),
    .dq_in(ctrl_dq_out),
    .dq_out(model_dq_out), .dq_oe(model_dq_oe),
    .dqm(phy_dqm),
    .bd_we(1'b0), .bd_word_addr(24'b0), .bd_wdata(32'b0),
    .bd_rd_word_addr(24'b0), .bd_rd_data(),
    .wr_evt(), .wr_evt_hw_addr(), .wr_evt_dqm()
);

assign model_errors = $unsigned(sdram_chip.errors);
assign ctrl_state   = sdram_ctrl.state;

endmodule
