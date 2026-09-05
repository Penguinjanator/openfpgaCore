//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------
//
// tb_clk_autotune.v — the self-tuning clock FSM against the REAL
// altera_pll_reconfig IP (sys/pll_cfg — production mgmt logic, DPRIO
// engine and all; only the two vendor externals are stubbed).
//
// The C++ harness (tb_clk_autotune_main.cpp) drives both clocks with
// real period ratios, plays the bridge (quiet handshake) and the PLL
// (locked; clk_sys retimed to 90 MHz once the DPRIO traffic has been
// observed), and asserts the full protocol ordering:
//     pause -> quiet -> warm reset -> 9 C-counter writes + START ->
//     frequency confirmation -> reset release -> pause release.
// The DPRIO write stream is decoded straight off reconfig_to_pll.
//

`default_nettype none

module tb_clk_autotune (
    input  wire        clk50,
    input  wire        clk_sys,
    input  wire        pll_locked,
    input  wire        req_switch,
    input  wire        bridge_quiet,
    output wire        bridge_pause,
    output wire        warm_reset,
    output wire        clk_is_90,
    output wire        attempted,
    output wire        switch_failed,
    output wire [31:0] freq_hz,

    // DPRIO bus taps (reconfig_to_pll bit map per altera_pll_reconfig_core)
    output wire        dprio_write,
    output wire [5:0]  dprio_addr,
    output wire [15:0] dprio_din,
    output wire [4:0]  dprio_cntsel
);

    wire [63:0] to_pll;

    // reconfig_from_pll carries the PLL-side readbacks the IP consumes:
    // [15:0] dprio_readdata (zeros fine), [16] locked, [17] phase_done.
    wire [63:0] from_pll = {46'd0, 1'b1, pll_locked, 16'd0};

    clk_autotune dut (
        .clk50             (clk50),
        .clk_sys           (clk_sys),
        .pll_locked        (pll_locked),
        .reconfig_to_pll   (to_pll),
        .reconfig_from_pll (from_pll),
        .req_switch        (req_switch),
        .bridge_pause      (bridge_pause),
        .bridge_quiet      (bridge_quiet),
        .warm_reset        (warm_reset),
        .clk_is_90         (clk_is_90),
        .attempted         (attempted),
        .switch_failed     (switch_failed),
        .freq_hz           (freq_hz)
    );

    assign dprio_write  = to_pll[2];
    assign dprio_addr   = to_pll[9:4];
    assign dprio_din    = to_pll[25:10];
    assign dprio_cntsel = to_pll[36:32];

endmodule

`default_nettype wire
