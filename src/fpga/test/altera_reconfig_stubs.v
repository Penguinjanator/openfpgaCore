//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------
// Simulation stubs for the vendor primitives referenced by the REAL
// altera_pll_reconfig IP (sys/pll_cfg/*) so tb_clk_autotune can compile
// the production mgmt logic under Verilator.  generic_lcell_comb and the
// dprio machinery are defined inside altera_pll_reconfig_core.v itself;
// these cover the externals.  The MIF readers live in dead generate
// branches (ENABLE_MIF=0) but Verilator still pin-checks them — port
// lists transcribed from the instantiations in altera_pll_reconfig_top.v.

// 2/3-FF synchronizer (matches the altera_std_synchronizer contract).
module altera_std_synchronizer #(
    parameter depth = 3
) (
    input  wire clk,
    input  wire reset_n,
    input  wire din,
    output wire dout
);
    reg [depth-1:0] sync_r;
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) sync_r <= {depth{1'b0}};
        else          sync_r <= {sync_r[depth-2:0], din};
    end
    assign dout = sync_r[depth-1];
endmodule

// MIF readers: never elaborated (ENABLE_MIF=0) — parse/pin-check stubs.
module altera_pll_reconfig_mif_reader #(
    parameter RECONFIG_ADDR_WIDTH = 6,
    parameter RECONFIG_DATA_WIDTH = 32,
    parameter ROM_ADDR_WIDTH = 9,
    parameter ROM_DATA_WIDTH = 32,
    parameter ROM_NUM_WORDS = 512,
    parameter DEVICE_FAMILY = "Cyclone V",
    parameter ENABLE_MIF = 0,
    parameter MIF_FILE_NAME = ""
) (
    input  wire mif_clk,
    input  wire mif_rst,
    input  wire reconfig_busy,
    input  wire [RECONFIG_DATA_WIDTH-1:0] reconfig_read_data,
    output wire [RECONFIG_DATA_WIDTH-1:0] reconfig_write_data,
    output wire [RECONFIG_ADDR_WIDTH-1:0] reconfig_addr,
    output wire reconfig_write,
    output wire reconfig_read,
    input  wire [ROM_ADDR_WIDTH-1:0] mif_base_addr,
    input  wire mif_start,
    output wire mif_busy
);
    assign reconfig_write_data = {RECONFIG_DATA_WIDTH{1'b0}};
    assign reconfig_addr = {RECONFIG_ADDR_WIDTH{1'b0}};
    assign reconfig_write = 1'b0;
    assign reconfig_read = 1'b0;
    assign mif_busy = 1'b0;
endmodule

module twentynm_pll_reconfig_mif_reader #(
    parameter RECONFIG_ADDR_WIDTH = 6,
    parameter RECONFIG_DATA_WIDTH = 32,
    parameter ROM_ADDR_WIDTH = 9,
    parameter ROM_DATA_WIDTH = 32,
    parameter ROM_NUM_WORDS = 512,
    parameter DEVICE_FAMILY = "Arria 10",
    parameter ENABLE_MIF = 0,
    parameter MIF_FILE_NAME = ""
) (
    input  wire mif_clk,
    input  wire mif_rst,
    input  wire reconfig_waitrequest,
    output wire [RECONFIG_DATA_WIDTH-1:0] reconfig_write_data,
    output wire [RECONFIG_ADDR_WIDTH-1:0] reconfig_addr,
    output wire reconfig_write,
    output wire reconfig_read,
    input  wire [ROM_ADDR_WIDTH-1:0] mif_base_addr,
    input  wire mif_start,
    output wire mif_busy
);
    assign reconfig_write_data = {RECONFIG_DATA_WIDTH{1'b0}};
    assign reconfig_addr = {RECONFIG_ADDR_WIDTH{1'b0}};
    assign reconfig_write = 1'b0;
    assign reconfig_read = 1'b0;
    assign mif_busy = 1'b0;
endmodule

// Arria-10 reconfig core: dead generate branch on Cyclone V builds.
module twentynm_iopll_reconfig_core #(
    parameter WAIT_FOR_LOCK = 1
) (
    input  wire mgmt_clk,
    input  wire mgmt_rst_n,
    input  wire mgmt_read,
    input  wire mgmt_write,
    input  wire [5:0]  mgmt_address,
    input  wire [31:0] mgmt_writedata,
    output wire [31:0] mgmt_readdata,
    output wire mgmt_waitrequest,
    output wire [63:0] reconfig_to_pll,
    input  wire [63:0] reconfig_from_pll
);
    assign mgmt_readdata = 32'd0;
    assign mgmt_waitrequest = 1'b0;
    assign reconfig_to_pll = 64'd0;
endmodule

// Family lcell primitives referenced by generic_lcell_comb (only the
// Cyclone V branch elaborates; the others are pin-checked).  Behavioral
// 6-input LUT honoring lut_mask.
module cyclonev_lcell_comb #(
    parameter lut_mask   = 64'hAAAAAAAAAAAAAAAA,
    parameter dont_touch = "on"
) (
    input  dataa, datab, datac, datad, datae, dataf,
    output combout
);
    wire [5:0] sel = {dataf, datae, datad, datac, datab, dataa};
    assign combout = lut_mask[sel];
endmodule

module stratixv_lcell_comb #(
    parameter lut_mask   = 64'hAAAAAAAAAAAAAAAA,
    parameter dont_touch = "on"
) (
    input  dataa, datab, datac, datad, datae, dataf,
    output combout
);
    wire [5:0] sel = {dataf, datae, datad, datac, datab, dataa};
    assign combout = lut_mask[sel];
endmodule

module arriav_lcell_comb #(
    parameter lut_mask   = 64'hAAAAAAAAAAAAAAAA,
    parameter dont_touch = "on"
) (
    input  dataa, datab, datac, datad, datae, dataf,
    output combout
);
    wire [5:0] sel = {dataf, datae, datad, datac, datab, dataa};
    assign combout = lut_mask[sel];
endmodule

module arriavgz_lcell_comb #(
    parameter lut_mask   = 64'hAAAAAAAAAAAAAAAA,
    parameter dont_touch = "on"
) (
    input  dataa, datab, datac, datad, datae, dataf,
    output combout
);
    wire [5:0] sel = {dataf, datae, datad, datac, datab, dataa};
    assign combout = lut_mask[sel];
endmodule
