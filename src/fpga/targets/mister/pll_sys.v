//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------

// Core PLLs for the MiSTer target (refclk = FPGA_CLK1_50 via sys_top).
//
// Two PLLs because 100 MHz and 24.576 MHz share no legal VCO on one
// (24.576/100 = 768/3125 — the common multiple is far outside the
// Cyclone V VCO range; the Pocket likewise sources video from its own
// PLL).  pll_sys is integer-mode; pll_vid is fractional.
//
//   pll_sys outclk_0  100.000 MHz @ 0 ps     clk_cpu / clk_ram_controller
//   pll_sys outclk_1  100.000 MHz @ 6750 ps  clk_ram_chip (SDRAM CK — the
//                                            Pocket's shipping phase;
//                                            re-tune on hardware if read
//                                            capture is marginal)
//   pll_vid outclk_0   24.576 MHz @ 0 ps     clk_vid (scanout pixel clock)
//
// The pll_sys hierarchy deliberately matches MiSTer's generated pll
// wrappers (pll → pll_inst → altera_pll_i): sys_top.sdc's exclusive
// clock-group wildcard `*|pll|pll_inst|altera_pll_i|*[*].*|divclk` must
// match these clocks.  Instantiate pll_sys with the name `pll`; pll_vid
// gets its own async group in mister.sdc.

`timescale 1ns/10ps

module pll_sys (
    input  wire refclk,
    input  wire rst,
    output wire outclk_0,
    output wire outclk_1,
`ifdef INCLUDE_CLK_AUTOTUNE
    input  wire [63:0] reconfig_to_pll,
    output wire [63:0] reconfig_from_pll,
`endif
    output wire locked
);

    pll_sys_0002 pll_inst (
        .refclk   (refclk),
        .rst      (rst),
        .outclk_0 (outclk_0),
        .outclk_1 (outclk_1),
`ifdef INCLUDE_CLK_AUTOTUNE
        .reconfig_to_pll   (reconfig_to_pll),
        .reconfig_from_pll (reconfig_from_pll),
`endif
        .locked   (locked)
    );

endmodule

module pll_sys_0002 (
    input  wire refclk,
    input  wire rst,
    output wire outclk_0,
    output wire outclk_1,
`ifdef INCLUDE_CLK_AUTOTUNE
    input  wire [63:0] reconfig_to_pll,
    output wire [63:0] reconfig_from_pll,
`endif
    output wire locked
);

`ifdef INCLUDE_CLK_AUTOTUNE
    // ------------------------------------------------------------------
    // Self-tuning clock (clk_autotune.v drives the reconfig bus).
    //
    // Reconfigurable-subtype PLL at VCO 900 MHz — the unique legal VCO
    // where BOTH system clocks are plain C-counter divisions:
    //     C0 = /9  -> 100.000 MHz   (compile-time default; STA closes here)
    //     C0 = /10 ->  90.000 MHz   (runtime fallback for marginal SDRAM)
    // The runtime switch rewrites ONLY C counters: M/N (and so the VCO)
    // are untouched, the PLL never loses lock, and both divisions give
    // EXACT 50% duty (odd /9 uses the odd_div_duty half-VCO-cycle trick),
    // so the DDIO-inverted SDRAM CK relationship is preserved in both
    // modes.  outclk_1 (180 MHz) only loads a keepalive FF; a runtime
    // rewrite lands on it harmlessly (clk_autotune writes ALL nine
    // physical counters because the FITTER assigns logical->physical
    // counter mapping: this fit maps outclk_0 -> shiften[7] — a
    // hardcoded cnt_sel would target a fit-dependent counter).
    //
    // The advanced parameters below are transcribed from the post-fit
    // atoms of the SAME configuration auto-derived by Q17
    // (bld/plltest/cfgD0, 2026-09-04): cp_current 10, bwctrl 6000,
    // vco_div 1, normal-mode feedback glb/fb_1, mimic gclk_far.  The
    // Reconfigurable twin (cfgD1) fits to the identical fpll atom
    // configuration and derives multiply_by 18 / divide_by 9 & 5 at 50%
    // duty (fit.rpt VCO 900.0 MHz).
    // ------------------------------------------------------------------
    altera_pll #(
        .fractional_vco_multiplier("false"),
        .reference_clock_frequency("50.0 MHz"),
        .operation_mode("normal"),
        .number_of_clocks(2),
        .output_clock_frequency0("100.000000 MHz"),
        .phase_shift0("0 ps"),
        .duty_cycle0(50),
        .output_clock_frequency1("180.000000 MHz"),
        .phase_shift1("0 ps"),
        .duty_cycle1(50),
        .output_clock_frequency2("0 MHz"),
        .phase_shift2("0 ps"),
        .duty_cycle2(50),
        .output_clock_frequency3("0 MHz"),
        .phase_shift3("0 ps"),
        .duty_cycle3(50),
        .output_clock_frequency4("0 MHz"),
        .phase_shift4("0 ps"),
        .duty_cycle4(50),
        .output_clock_frequency5("0 MHz"),
        .phase_shift5("0 ps"),
        .duty_cycle5(50),
        .output_clock_frequency6("0 MHz"),
        .phase_shift6("0 ps"),
        .duty_cycle6(50),
        .output_clock_frequency7("0 MHz"),
        .phase_shift7("0 ps"),
        .duty_cycle7(50),
        .output_clock_frequency8("0 MHz"),
        .phase_shift8("0 ps"),
        .duty_cycle8(50),
        .output_clock_frequency9("0 MHz"),
        .phase_shift9("0 ps"),
        .duty_cycle9(50),
        .output_clock_frequency10("0 MHz"),
        .phase_shift10("0 ps"),
        .duty_cycle10(50),
        .output_clock_frequency11("0 MHz"),
        .phase_shift11("0 ps"),
        .duty_cycle11(50),
        .output_clock_frequency12("0 MHz"),
        .phase_shift12("0 ps"),
        .duty_cycle12(50),
        .output_clock_frequency13("0 MHz"),
        .phase_shift13("0 ps"),
        .duty_cycle13(50),
        .output_clock_frequency14("0 MHz"),
        .phase_shift14("0 ps"),
        .duty_cycle14(50),
        .output_clock_frequency15("0 MHz"),
        .phase_shift15("0 ps"),
        .duty_cycle15(50),
        .output_clock_frequency16("0 MHz"),
        .phase_shift16("0 ps"),
        .duty_cycle16(50),
        .output_clock_frequency17("0 MHz"),
        .phase_shift17("0 ps"),
        .duty_cycle17(50),
        .pll_type("Cyclone V"),
        .pll_subtype("Reconfigurable"),
        .m_cnt_hi_div(9),
        .m_cnt_lo_div(9),
        .n_cnt_hi_div(256),
        .n_cnt_lo_div(256),
        .m_cnt_bypass_en("false"),
        .n_cnt_bypass_en("true"),
        .m_cnt_odd_div_duty_en("false"),
        .n_cnt_odd_div_duty_en("false"),
        .c_cnt_hi_div0(5),
        .c_cnt_lo_div0(4),
        .c_cnt_prst0(1),
        .c_cnt_ph_mux_prst0(0),
        .c_cnt_in_src0("ph_mux_clk"),
        .c_cnt_bypass_en0("false"),
        .c_cnt_odd_div_duty_en0("true"),
        .c_cnt_hi_div1(3),
        .c_cnt_lo_div1(2),
        .c_cnt_prst1(1),
        .c_cnt_ph_mux_prst1(0),
        .c_cnt_in_src1("ph_mux_clk"),
        .c_cnt_bypass_en1("false"),
        .c_cnt_odd_div_duty_en1("true"),
        .c_cnt_hi_div2(1),
        .c_cnt_lo_div2(1),
        .c_cnt_prst2(1),
        .c_cnt_ph_mux_prst2(0),
        .c_cnt_in_src2("ph_mux_clk"),
        .c_cnt_bypass_en2("true"),
        .c_cnt_odd_div_duty_en2("false"),
        .c_cnt_hi_div3(1),
        .c_cnt_lo_div3(1),
        .c_cnt_prst3(1),
        .c_cnt_ph_mux_prst3(0),
        .c_cnt_in_src3("ph_mux_clk"),
        .c_cnt_bypass_en3("true"),
        .c_cnt_odd_div_duty_en3("false"),
        .c_cnt_hi_div4(1),
        .c_cnt_lo_div4(1),
        .c_cnt_prst4(1),
        .c_cnt_ph_mux_prst4(0),
        .c_cnt_in_src4("ph_mux_clk"),
        .c_cnt_bypass_en4("true"),
        .c_cnt_odd_div_duty_en4("false"),
        .c_cnt_hi_div5(1),
        .c_cnt_lo_div5(1),
        .c_cnt_prst5(1),
        .c_cnt_ph_mux_prst5(0),
        .c_cnt_in_src5("ph_mux_clk"),
        .c_cnt_bypass_en5("true"),
        .c_cnt_odd_div_duty_en5("false"),
        .c_cnt_hi_div6(1),
        .c_cnt_lo_div6(1),
        .c_cnt_prst6(1),
        .c_cnt_ph_mux_prst6(0),
        .c_cnt_in_src6("ph_mux_clk"),
        .c_cnt_bypass_en6("true"),
        .c_cnt_odd_div_duty_en6("false"),
        .c_cnt_hi_div7(1),
        .c_cnt_lo_div7(1),
        .c_cnt_prst7(1),
        .c_cnt_ph_mux_prst7(0),
        .c_cnt_in_src7("ph_mux_clk"),
        .c_cnt_bypass_en7("true"),
        .c_cnt_odd_div_duty_en7("false"),
        .c_cnt_hi_div8(1),
        .c_cnt_lo_div8(1),
        .c_cnt_prst8(1),
        .c_cnt_ph_mux_prst8(0),
        .c_cnt_in_src8("ph_mux_clk"),
        .c_cnt_bypass_en8("true"),
        .c_cnt_odd_div_duty_en8("false"),
        .c_cnt_hi_div9(1),
        .c_cnt_lo_div9(1),
        .c_cnt_prst9(1),
        .c_cnt_ph_mux_prst9(0),
        .c_cnt_in_src9("ph_mux_clk"),
        .c_cnt_bypass_en9("true"),
        .c_cnt_odd_div_duty_en9("false"),
        .c_cnt_hi_div10(1),
        .c_cnt_lo_div10(1),
        .c_cnt_prst10(1),
        .c_cnt_ph_mux_prst10(0),
        .c_cnt_in_src10("ph_mux_clk"),
        .c_cnt_bypass_en10("true"),
        .c_cnt_odd_div_duty_en10("false"),
        .c_cnt_hi_div11(1),
        .c_cnt_lo_div11(1),
        .c_cnt_prst11(1),
        .c_cnt_ph_mux_prst11(0),
        .c_cnt_in_src11("ph_mux_clk"),
        .c_cnt_bypass_en11("true"),
        .c_cnt_odd_div_duty_en11("false"),
        .c_cnt_hi_div12(1),
        .c_cnt_lo_div12(1),
        .c_cnt_prst12(1),
        .c_cnt_ph_mux_prst12(0),
        .c_cnt_in_src12("ph_mux_clk"),
        .c_cnt_bypass_en12("true"),
        .c_cnt_odd_div_duty_en12("false"),
        .c_cnt_hi_div13(1),
        .c_cnt_lo_div13(1),
        .c_cnt_prst13(1),
        .c_cnt_ph_mux_prst13(0),
        .c_cnt_in_src13("ph_mux_clk"),
        .c_cnt_bypass_en13("true"),
        .c_cnt_odd_div_duty_en13("false"),
        .c_cnt_hi_div14(1),
        .c_cnt_lo_div14(1),
        .c_cnt_prst14(1),
        .c_cnt_ph_mux_prst14(0),
        .c_cnt_in_src14("ph_mux_clk"),
        .c_cnt_bypass_en14("true"),
        .c_cnt_odd_div_duty_en14("false"),
        .c_cnt_hi_div15(1),
        .c_cnt_lo_div15(1),
        .c_cnt_prst15(1),
        .c_cnt_ph_mux_prst15(0),
        .c_cnt_in_src15("ph_mux_clk"),
        .c_cnt_bypass_en15("true"),
        .c_cnt_odd_div_duty_en15("false"),
        .c_cnt_hi_div16(1),
        .c_cnt_lo_div16(1),
        .c_cnt_prst16(1),
        .c_cnt_ph_mux_prst16(0),
        .c_cnt_in_src16("ph_mux_clk"),
        .c_cnt_bypass_en16("true"),
        .c_cnt_odd_div_duty_en16("false"),
        .c_cnt_hi_div17(1),
        .c_cnt_lo_div17(1),
        .c_cnt_prst17(1),
        .c_cnt_ph_mux_prst17(0),
        .c_cnt_in_src17("ph_mux_clk"),
        .c_cnt_bypass_en17("true"),
        .c_cnt_odd_div_duty_en17("false"),
        .pll_vco_div(1),
        .pll_cp_current(10),
        .pll_bwctrl(6000),
        .pll_output_clk_frequency("900.000000 MHz"),
        .pll_fractional_division("1"),
        .mimic_fbclk_type("gclk_far"),
        .pll_fbclk_mux_1("glb"),
        .pll_fbclk_mux_2("fb_1"),
        .pll_m_cnt_in_src("ph_mux_clk"),
        .pll_slf_rst("false")
    ) altera_pll_i (
        .rst    (rst),
        .outclk ({outclk_1, outclk_0}),
        .locked (locked),
        .fboutclk (),
        .fbclk  (1'b0),
        .refclk (refclk),
        .reconfig_to_pll   (reconfig_to_pll),
        .reconfig_from_pll (reconfig_from_pll)
    );

    // outclk_1's one real load (same role as the CLK90 keepalive below):
    // keeps the 180 MHz counter alive so the fit keeps both counters
    // programmed.  The VCO itself is pinned by the explicit M/N above.
    reg vco_keepalive_at /* synthesis noprune */;
    always @(posedge outclk_1) vco_keepalive_at <= ~vco_keepalive_at;

`else  /* !INCLUDE_CLK_AUTOTUNE — fixed-frequency configurations */

    wire unused_outclk2;
    wire unused_outclk3;
    wire unused_outclk4;

    altera_pll #(
        .fractional_vco_multiplier("false"),
        .reference_clock_frequency("50.0 MHz"),
        .operation_mode("normal"),
        .number_of_clocks(5),
`ifdef INCLUDE_CLK90
        // 90 MHz build: extra period everywhere (address/command setup into
        // heavily-loaded pluggable SDRAM modules included).
        //
        // outclk_1 (216 MHz) exists ONLY to force a legal VCO.  Q17's
        // auto-derive works on the POST-PRUNE netlist: with outclk_1
        // dangling it derived M=36/N=5 = VCO 360 MHz from the 90 MHz
        // output alone — far below the Cyclone V 600 MHz floor.  It locks
        // and clk_sys runs, but the SDRAM read path dies (HW 2026-08-26:
        // reads return all-zeros, black boot).  Requesting 216 here is not
        // enough — the counter must SURVIVE pruning, hence the noprune
        // keepalive FF below.  With it, auto-derive picks M=108/N=5 =
        // VCO 1080 (C=12 -> 90, C=5 -> 216), mid-band legal (600-1300).
        // 180 MHz would NOT work even kept (LCM(90,180)=360 again).
        // (Isolated-fit matrix, bld/plltest, 2026-08-25.  Baseline note:
        // the 100 MHz config auto-derives VCO 500 — also sub-floor, like
        // canonical MiSTer's pll_hdmi 445/pll_audio 418, and field-proven
        // regardless; 360 is where real silicon stopped delivering.)
        .output_clock_frequency0("90.000000 MHz"),
        .phase_shift0("0 ps"),
        .duty_cycle0(50),
        .output_clock_frequency1("216.000000 MHz"),
        .phase_shift1("0 ps"),
        .duty_cycle1(50),
`else
        .output_clock_frequency0("100.000000 MHz"),
        .phase_shift0("0 ps"),
        .duty_cycle0(50),
        .output_clock_frequency1("100.000000 MHz"),
        .phase_shift1("6750 ps"),
        .duty_cycle1(50),
`endif
        .output_clock_frequency2("0 MHz"),
        .phase_shift2("0 ps"),
        .duty_cycle2(50),
        .output_clock_frequency3("0 MHz"),
        .phase_shift3("0 ps"),
        .duty_cycle3(50),
        .output_clock_frequency4("0 MHz"),
        .phase_shift4("0 ps"),
        .duty_cycle4(50),
        .pll_type("General"),
        .pll_subtype("General")
    ) altera_pll_i (
        .rst    (rst),
        .outclk ({unused_outclk4, unused_outclk3, unused_outclk2, outclk_1, outclk_0}),
        .locked (locked),
        .fboutclk (),
        .fbclk  (1'b0),
        .refclk (refclk)
    );

`ifdef INCLUDE_CLK90
    // VCO keepalive: outclk_1's one real load.  Without it the fitter
    // prunes the general[1] counter and re-derives the VCO from 90 MHz
    // alone = an illegal 360 MHz (see the parameter comment above).  One
    // FF, no fanout; sys_top.sdc's derive_pll_clocks constrains the
    // resulting 216 MHz domain (self-loop only, trivially met).
    reg vco_keepalive /* synthesis noprune */;
    always @(posedge outclk_1) vco_keepalive <= ~vco_keepalive;
`endif

`endif /* !INCLUDE_CLK_AUTOTUNE */

endmodule

module pll_vid (
    input  wire refclk,
    input  wire rst,
    output wire outclk_0,
    output wire locked
);

    pll_vid_0002 pll_inst (
        .refclk   (refclk),
        .rst      (rst),
        .outclk_0 (outclk_0),
        .locked   (locked)
    );

endmodule

module pll_vid_0002 (
    input  wire refclk,
    input  wire rst,
    output wire outclk_0,
    output wire locked
);

    wire unused_outclk1;
    wire unused_outclk2;
    wire unused_outclk3;
    wire unused_outclk4;

    altera_pll #(
        .fractional_vco_multiplier("true"),
        .reference_clock_frequency("50.0 MHz"),
        .operation_mode("normal"),
        .number_of_clocks(5),
        .output_clock_frequency0("24.576000 MHz"),
        .phase_shift0("0 ps"),
        .duty_cycle0(50),
        .output_clock_frequency1("0 MHz"),
        .phase_shift1("0 ps"),
        .duty_cycle1(50),
        .output_clock_frequency2("0 MHz"),
        .phase_shift2("0 ps"),
        .duty_cycle2(50),
        .output_clock_frequency3("0 MHz"),
        .phase_shift3("0 ps"),
        .duty_cycle3(50),
        .output_clock_frequency4("0 MHz"),
        .phase_shift4("0 ps"),
        .duty_cycle4(50),
        .pll_type("General"),
        .pll_subtype("General")
    ) altera_pll_i (
        .rst    (rst),
        .outclk ({unused_outclk4, unused_outclk3, unused_outclk2, unused_outclk1, outclk_0}),
        .locked (locked),
        .fboutclk (),
        .fbclk  (1'b0),
        .refclk (refclk)
    );

endmodule
