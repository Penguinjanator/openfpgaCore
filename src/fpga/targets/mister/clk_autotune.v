//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------
//
// clk_autotune — self-tuning system clock for the MiSTer target
// (INCLUDE_CLK_AUTOTUNE).
//
// One bitstream, two SDRAM-proven clock profiles:
//     100 MHz (compile-time default, STA-closed) and 90 MHz (fallback for
//     marginal pluggable modules — the DE10 dual-chip class, HW-proven by
//     the mister90 variant).
//
// The boot ROM probes SDRAM at 100 MHz first thing (BRAM code, immune to
// bad SDRAM).  On failure it writes HPS_CLK_REQ_MAGIC to HPS_CLK_CTRL;
// this module then:
//   1. PAUSES hps_bridge (ingress backpressured via ioctl_wait, no new
//      AXI issue; ALL stream state kept — a mid-flight ini/elf download
//      just stalls and resumes, Main never notices),
//   2. asserts a WARM RESET over the clk_sys core domain (CPU, periph,
//      GPU, scanout, arbiter masters) plus a dedicated reset for
//      io_sdram (its ST_RESET drives CKE low + NOP, and it re-runs the
//      full JEDEC init on release; DRAM contents survive — the whole
//      switch window is far under the 64 ms refresh budget),
//   3. rewrites the PLL C counters to /10 (90 MHz) through the
//      altera_pll_reconfig IP.  ALL NINE physical counters are written
//      because the fitter assigns logical->physical counter mapping
//      per fit (this fit: outclk_0 = shiften[7]); the same /10 value is
//      correct for both live counters (clk_sys and the keepalive) and
//      harmless on unused ones.  M/N — and so the VCO — are untouched:
//      the PLL never loses lock,
//   4. CONFIRMS the new frequency with a hardware frequency meter
//      (clk_sys edges counted against the 50 MHz reference), then
//      releases the warm reset and, last, the bridge pause.
//
// The CPU re-enters the boot ROM from BRAM at 90 MHz, re-probes, and
// continues the normal boot.  The decision is sticky until power-off /
// core reload; a second request is ignored (attempted=1) so a board
// that is broken even at 90 halts with a readable banner instead of
// looping.  OSD/status[0] soft resets do NOT touch this module.
//
// Clock domains:
//   clk50   — FSM + mgmt Avalon (stable through the switch).
//   clk_sys — only the gray-code frequency counter; it is never reset
//             and keeps counting through the switch.
//   The req/pause/quiet/status crossings are quasi-static levels through
//   2-FF synchronizers; every one of them is STATIC during the counter
//   rewrite window, so runt clock pulses cannot corrupt state (D == Q).
//
`timescale 1ns/10ps
`default_nettype none

module clk_autotune (
    input  wire        clk50,             // FPGA_CLK1_50 via emu CLK_50M
    input  wire        clk_sys,           // the clock being tuned (measured)
    input  wire        pll_locked,

    // PLL reconfig bus (pll_sys reconfig ports)
    output wire [63:0] reconfig_to_pll,
    input  wire [63:0] reconfig_from_pll,

    // Request (clk_sys domain level; cleared by the warm reset it causes)
    input  wire        req_switch,

    // Bridge pause handshake (hps_bridge, clk_sys domain)
    output reg         bridge_pause,
    input  wire        bridge_quiet,

    // Warm reset out (active high).  emu.sv folds it into reset_n and
    // drives io_sdram's dedicated reset_n with the inverse.
    output reg         warm_reset,

    // Status (quasi-static; consumers 2-FF sync in their own domain)
    output reg         clk_is_90,         // switch performed AND confirmed
    output reg         attempted,         // a switch was requested/performed
    output reg         switch_failed,     // rewrite done but 90 MHz never confirmed
    output reg  [31:0] freq_hz            // measured clk_sys frequency
);

    // ------------------------------------------------------------------
    // C-counter write value: /10 = hi 5, lo 5, even division (exact 50%
    // duty), no bypass.  {cnt_sel[22:18], odd[17], bypass[16], hi[15:8],
    // lo[7:0]} per altera_pll_reconfig_core C_COUNTERS_REG.
    // ------------------------------------------------------------------
    localparam [31:0] C_DIV10_BASE = {9'd0, 5'd0, 1'b0, 1'b0, 8'd5, 8'd5};
    localparam [5:0]  ADDR_C_CNT   = 6'd5;
    localparam [5:0]  ADDR_START   = 6'd2;

    // 90 MHz confirmation window: 88_000..92_000 kHz.
    localparam [31:0] F90_LO_KHZ = 32'd88_000;
    localparam [31:0] F90_HI_KHZ = 32'd92_000;

    // ------------------------------------------------------------------
    // Reconfig IP (same altera_pll_reconfig instance the framework uses
    // for pll_hdmi).  WAIT_FOR_LOCK=1: mgmt_waitrequest stays asserted
    // through each DPRIO transaction and through START-until-locked.
    // ------------------------------------------------------------------
    reg         mgmt_write;
    reg  [5:0]  mgmt_address;
    reg  [31:0] mgmt_writedata;
    wire        mgmt_waitrequest;
    wire [31:0] mgmt_readdata;

    // Power-on reset for the IP's DPRIO init readback.
    reg [6:0] por_cnt = 7'd0;
    wire      por_done = por_cnt[6];
    always @(posedge clk50)
        if (!por_done) por_cnt <= por_cnt + 7'd1;

    pll_cfg cfg_sys (
        .mgmt_clk          (clk50),
        .mgmt_reset        (~por_done),
        .mgmt_waitrequest  (mgmt_waitrequest),
        .mgmt_read         (1'b0),
        .mgmt_write        (mgmt_write),
        .mgmt_readdata     (mgmt_readdata),
        .mgmt_address      (mgmt_address),
        .mgmt_writedata    (mgmt_writedata),
        .reconfig_to_pll   (reconfig_to_pll),
        .reconfig_from_pll (reconfig_from_pll)
    );

    // ------------------------------------------------------------------
    // Frequency meter.  Free-running gray counter in the clk_sys domain
    // (never reset — it must count straight through the switch), sampled
    // in clk50 over a 1 ms window: delta = clk_sys kHz.
    // ------------------------------------------------------------------
    reg  [23:0] fmeter_bin = 24'd0;
    reg  [23:0] fmeter_gray = 24'd0;
    always @(posedge clk_sys) begin
        fmeter_bin  <= fmeter_bin + 24'd1;
        fmeter_gray <= (fmeter_bin + 24'd1) ^ ((fmeter_bin + 24'd1) >> 1);
    end

    reg [23:0] gray_s1, gray_s2;
    always @(posedge clk50) begin
        gray_s1 <= fmeter_gray;
        gray_s2 <= gray_s1;
    end
    // gray -> binary
    integer gi;
    reg [23:0] fmeter_now;
    always @(*) begin
        fmeter_now[23] = gray_s2[23];
        for (gi = 22; gi >= 0; gi = gi - 1)
            fmeter_now[gi] = fmeter_now[gi + 1] ^ gray_s2[gi];
    end

    reg [15:0] win_cnt = 16'd0;          // 50_000 clk50 cycles = 1 ms
    reg [23:0] win_start = 24'd0;
    reg [31:0] freq_khz = 32'd0;
    always @(posedge clk50) begin
        if (win_cnt == 16'd49_999) begin
            win_cnt   <= 16'd0;
            // 24-bit wraps every ~186 ms at 90 MHz — the 1 ms delta is
            // safely inside one wrap.
            freq_khz  <= {8'd0, fmeter_now - win_start};
            win_start <= fmeter_now;
        end else
            win_cnt <= win_cnt + 16'd1;
    end
    always @(posedge clk50)
        freq_hz <= freq_khz * 32'd1000;

    wire freq_is_90 = (freq_khz >= F90_LO_KHZ) && (freq_khz <= F90_HI_KHZ);

    // ------------------------------------------------------------------
    // Request / bridge-quiet CDC (levels).
    // ------------------------------------------------------------------
    reg [1:0] req_sync = 2'b00;
    reg [1:0] quiet_sync = 2'b00;
    reg [1:0] locked_sync = 2'b00;
    always @(posedge clk50) begin
        req_sync    <= {req_sync[0], req_switch};
        quiet_sync  <= {quiet_sync[0], bridge_quiet};
        locked_sync <= {locked_sync[0], pll_locked};
    end

    // ------------------------------------------------------------------
    // FSM
    // ------------------------------------------------------------------
    localparam S_IDLE        = 4'd0;
    localparam S_PAUSE       = 4'd1;   // bridge_pause, wait drained
    localparam S_QUIET       = 4'd2;   // require quiet stable a while
    localparam S_RESET_IN    = 4'd3;   // warm reset, let fabric drain
    localparam S_WR_SETUP    = 4'd4;   // present one C-counter write
    localparam S_WR_WAIT     = 4'd5;   // hold write until !waitrequest
    localparam S_START_SETUP = 4'd6;
    localparam S_START_WAIT  = 4'd7;
    localparam S_CONFIRM     = 4'd8;   // wait for 90 MHz on the meter
    localparam S_SETTLE      = 4'd9;   // post-confirm reset hold
    localparam S_RELEASE     = 4'd10;  // drop warm reset, then pause
    localparam S_DONE        = 4'd11;

    reg [3:0]  state = S_IDLE;
    reg [3:0]  cnt_idx = 4'd0;
    reg [21:0] tmr = 22'd0;

    initial begin
        bridge_pause  = 1'b0;
        warm_reset    = 1'b0;
        clk_is_90     = 1'b0;
        attempted     = 1'b0;
        switch_failed = 1'b0;
        mgmt_write    = 1'b0;
        mgmt_address  = 6'd0;
        mgmt_writedata = 32'd0;
    end

    always @(posedge clk50) begin
        case (state)
        S_IDLE: begin
            // One-shot: a request is honored once per power-up/reload.
            if (req_sync[1] && !attempted && locked_sync[1] && por_done) begin
                attempted    <= 1'b1;
                bridge_pause <= 1'b1;
                tmr          <= 22'd0;
                state        <= S_PAUSE;
            end
        end

        // Bridge drains its slot/skid + in-flight AXI op; Main is
        // backpressured by ioctl_wait.  bridge_quiet also requires a
        // stretch of ioctl silence (see hps_bridge.v).
        S_PAUSE: begin
            if (quiet_sync[1]) begin
                tmr   <= 22'd0;
                state <= S_QUIET;
            end
        end

        // Quiet must HOLD ~10 us (a pulse of quiet between two stream
        // words must not launch the switch).
        S_QUIET: begin
            if (!quiet_sync[1]) begin
                state <= S_PAUSE;
            end else if (tmr == 22'd511) begin
                warm_reset <= 1'b1;
                tmr        <= 22'd0;
                state      <= S_RESET_IN;
            end else
                tmr <= tmr + 22'd1;
        end

        // With every master in reset and the bridge paused, any in-flight
        // SDRAM op (<= ~2 us) completes and the fabric goes static.
        // 1024 clk50 cycles = ~20 us.
        S_RESET_IN: begin
            if (tmr == 22'd1023) begin
                cnt_idx <= 4'd0;
                state   <= S_WR_SETUP;
            end else
                tmr <= tmr + 22'd1;
        end

        // Write /10 into physical C counters 0..8 (one DPRIO transaction
        // each; waitrequest covers the transfer).
        S_WR_SETUP: begin
            mgmt_address   <= ADDR_C_CNT;
            mgmt_writedata <= C_DIV10_BASE | ({28'd0, cnt_idx} << 18);
            mgmt_write     <= 1'b1;
            state          <= S_WR_WAIT;
        end
        S_WR_WAIT: begin
            if (mgmt_write && !mgmt_waitrequest) begin
                mgmt_write <= 1'b0;
                if (cnt_idx == 4'd8)
                    state <= S_START_SETUP;
                else begin
                    cnt_idx <= cnt_idx + 4'd1;
                    state   <= S_WR_SETUP;
                end
            end
        end

        S_START_SETUP: begin
            mgmt_address   <= ADDR_START;
            mgmt_writedata <= 32'd1;
            mgmt_write     <= 1'b1;
            state          <= S_START_WAIT;
        end
        S_START_WAIT: begin
            if (mgmt_write && !mgmt_waitrequest) begin
                mgmt_write <= 1'b0;
                tmr        <= 22'd0;
                state      <= S_CONFIRM;
            end
        end

        // Wait until the meter reads ~90 MHz (needs up to two 1 ms
        // windows after the counters land).  Timeout ~80 ms: proceed
        // anyway with switch_failed so the boot ROM can paint a readable
        // message (at whatever clock we actually run).
        S_CONFIRM: begin
            if (freq_is_90 && locked_sync[1]) begin
                clk_is_90 <= 1'b1;
                tmr       <= 22'd0;
                state     <= S_SETTLE;
            end else if (tmr == 22'h3F_FFFF) begin
                switch_failed <= 1'b1;
                tmr           <= 22'd0;
                state         <= S_SETTLE;
            end else
                tmr <= tmr + 22'd1;
        end

        // Hold reset a further ~40 us so the new clock is well settled
        // before logic runs on it.
        S_SETTLE: begin
            if (tmr == 22'd2047) begin
                warm_reset <= 1'b0;
                tmr        <= 22'd0;
                state      <= S_RELEASE;
            end else
                tmr <= tmr + 22'd1;
        end

        // Release the bridge only after the fabric is back up (~20 us);
        // its resumed AXI writes then meet a live arbiter (io_sdram is
        // still in its ~330 us JEDEC re-init — word ops simply queue).
        S_RELEASE: begin
            if (tmr == 22'd1023) begin
                bridge_pause <= 1'b0;
                state        <= S_DONE;
            end else
                tmr <= tmr + 22'd1;
        end

        S_DONE: begin
            // Sticky until the core is reloaded.
        end

        default: state <= S_IDLE;
        endcase
    end

endmodule

`default_nettype wire
