#!/usr/bin/env python3
"""Check DirectFB/audio arbitration with the production DMA request expression.

The sample producer is a conservative contention model, not a cycle-accurate
mixer. The separate audio-mixer-mister target checks the real mixer. This test
uses the real audio queue, video arbiter and framebuffer copy engine, and checks
both sample deadlines and pixel data. Bypassing the guard reproduces underflow.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

AUDIO_MODEL = r'''
// A paced sample producer that cannot make memory-dependent progress
// while a video burst owns SDRAM. This is a contention model, not a
// cycle-accurate implementation of the mixer (tested separately).
reg [11:0] audio_work;
reg [15:0] audio_id;
reg audio_wr;
reg [31:0] audio_data;
always @(posedge clk) begin
    audio_wr <= 0;
    if (!reset_n || !audio_enable) begin
        audio_work <= 0;
        audio_id <= 1;
        audio_data <= 0;
    end else if (audio_work == 0) begin
        if (!audio_fifo_full) audio_work <= 12'd1000;
    end else if (!sm_active) begin
        audio_work <= audio_work - 12'd1;
        if (audio_work == 1) begin
            audio_wr <= 1;
            audio_data <= {audio_id, ~audio_id};
            audio_id <= audio_id + 16'd1;
        end
    end
end
mister_audio_output audio_output (
    .clk(clk), .reset_n(reset_n), .mixer_enable(audio_enable),
    .clk_is90(audio_is90), .sample_wr(audio_wr), .sample_data(audio_data),
    .fifo_full(audio_fifo_full), .fifo_level(),
    .audio_l(audio_l), .audio_r(audio_r)
);

'''

AUDIO_CASES = r'''
    for (bool is90 : {false, true}) for (bool guard : {false, true})
    for (bool rgb : {false, true}) {
        tb->reset_n = 0; tb->enable = 0; tb->audio_enable = 0;
        tb->crt_vs = 0; tb->early_vblank = 0; tb->vid_kick = 0;
        steps(20);
        audio_last = audio_last_tick = audio_gaps = audio_order = audio_samples = 0;
        tb->reset_n = 1; tb->audio_enable = 1;
        tb->audio_guard = guard; tb->audio_is90 = is90;
        tb->color_mode = rgb ? 3 : 0;
        tb->fb_width = rgb ? 640 : 320; tb->fb_height = rgb ? 480 : 200;
        tb->fb_stride = rgb ? 1280 : 320;
        tb->fb_display_addr = SRC_HALF;
        tb->enable = 1; steps(40000);
        tb->crt_vs = 1; tb->early_vblank = 1; steps(20);
        tb->crt_vs = 0; tb->early_vblank = 0;
        unsigned deadline = is90 ? 1500000 : 1666667;
        unsigned completed = 0, requests = 0;
        for (unsigned cycle = 0; cycle < deadline; ++cycle) {
            tb->vid_kick = cycle % 3180 == 0;
            if (tb->vid_kick) {tb->vid_kick_addr = VID_HALF;tb->vid_kick_len = 160;requests++;}
            step();
            if (!completed && tb->FB_EN) completed = cycle;
        }
        tb->vid_kick = 0;
        steps(600);
        CHECK(tb->vid_done_cnt == requests, "audio refill never loses a priority scanout request");
        printf("audio DMA: %dMHz guard=%d rgb=%d samples=%u gaps=%u complete=%u cycles\n",
               is90?90:100,guard,rgb,audio_samples,audio_gaps,completed);
        CHECK(completed && completed < deadline, "frame completes within one refresh with audio and scanout");
        CHECK(frame_matches(SRC_HALF << 1, SLOT0, tb->fb_stride, tb->fb_height), "audio contention leaves the frame bit-exact");
        CHECK(!audio_order && audio_samples > 100, "audio samples stay ordered through contention");
        CHECK(guard ? audio_gaps == 0 : audio_gaps > 0, "audio guard prevents reproduced underflow");
        CHECK(tb->ddr_proto_err == 0 && tb->vid_err_cnt == 0, "no Avalon or priority scanout corruption");
    }
'''

AUDIO_MONITOR = r'''
    if (tb->audio_enable && tb->audio_l != audio_last) {
        if (audio_last) {
            unsigned interval = ticks - audio_last_tick;
            unsigned low = tb->audio_is90 ? 1875 : 2083;
            if (interval < low || interval > low + 1) audio_gaps++;
            if (tb->audio_l != uint16_t(audio_last + 1)) audio_order++;
        }
        if (tb->audio_r != uint16_t(~tb->audio_l)) audio_order++;
        audio_last = tb->audio_l;
        audio_last_tick = ticks;
        audio_samples++;
    }'''

def replace_once(source, before, after):
    if source.count(before) != 1:
        raise RuntimeError(f"fixture anchor changed: {before!r}")
    return source.replace(before, after, 1)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=root)
    parser.add_argument("--output", type=Path,
                        default=root / "build/mister-audio-contention")
    args = parser.parse_args()
    source = args.source_root.resolve() / "src/fpga"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixtures = root / "src/fpga/test"

    emu = (source / "targets/mister/emu.sv").read_text()
    arbiter = emu.split("video_burst_arb vburst_arb (", 1)[1].split(");", 1)[0]
    line, = [line.strip() for line in arbiter.splitlines() if ".dma_req(" in line]
    if not line.startswith(".dma_req(") or not line.endswith("),"):
        raise RuntimeError("cannot extract the production framebuffer request")
    expression = line[len(".dma_req("):-2]
    if emu.count("reg fbdma_audio_ready;") != 1:
        raise RuntimeError("cannot extract the registered DMA permission")
    guard = emu.split("reg fbdma_audio_ready;", 1)[1].split(
        "video_burst_arb vburst_arb (", 1)[0]
    guard = "reg fbdma_audio_ready;" + guard.replace(
        "clk_ram_controller", "clk").replace("reset_n_cpu_core", "reset_n")

    tb = (fixtures / "tb_ddr3_fb.v").read_text()
    tb = replace_once(tb, "    // scenario controls", """    input wire audio_enable,
    input wire audio_guard,
    input wire audio_is90,
    output wire [15:0] audio_l,
    output wire [15:0] audio_r,
    // scenario controls""")
    tb = replace_once(tb, "video_burst_arb arb (", """wire audio_fifo_full;
wire mixer_enable_mmio = audio_enable;
wire fbdma_req = dma_req;
video_burst_arb arb (""")
    tb = replace_once(tb, "video_burst_arb arb (", guard + "video_burst_arb arb (")
    tb = replace_once(tb, ".dma_req(dma_req), .dma_addr(dma_addr)",
                      ".dma_req(audio_guard ? (" + expression
                      + ") : fbdma_req), .dma_addr(dma_addr)")
    tb = replace_once(tb, "reg        sm_active;",
                      "reg        sm_active;\nreg sm_word_phase;")
    tb = replace_once(tb, "\n        sm_active <= 1'b0;",
                      "\n        sm_active <= 1'b0;\n        sm_word_phase <= 1'b0;")
    tb = replace_once(tb, "            sm_lat  <= 4'd8;",
                      "            sm_lat  <= 4'd8;\n            sm_word_phase <= 1'b0;")
    tb = replace_once(tb, "            end else if (sm_left != 11'd0) begin", """            end else if (sm_word_phase) begin
                sm_word_phase <= 1'b0;
            end else if (sm_left != 11'd0) begin
                // Two halfword transfers per 32-bit word on the SDRAM bus.
                sm_word_phase <= 1'b1;""")
    anchor = "// ---------------------------------------------------------------------------\n// DDR3 Avalon slave model:"
    tb = replace_once(tb, anchor, AUDIO_MODEL + anchor)
    (output / "tb_ddr3_audio.v").write_text(tb)

    cpp = (fixtures / "tb_ddr3_fb_main.cpp").read_text()
    cpp = replace_once(cpp, "static void step() {", """static unsigned audio_last, audio_last_tick, audio_gaps, audio_order, audio_samples;
static void step() {""")
    cpp = replace_once(cpp, "    ticks++;", "    ticks++;\n" + AUDIO_MONITOR)
    cpp = replace_once(cpp, "    // reset\n", """    tb->audio_enable = 0; tb->audio_guard = 1; tb->audio_is90 = 0;
    // reset
""")
    anchor = '    printf("=== Results: %d passed, %d failed ===\\n", pass, fail);'
    cpp = replace_once(cpp, anchor, AUDIO_CASES + anchor)
    (output / "tb_ddr3_audio_main.cpp").write_text(cpp)

    verilator = shutil.which("verilator")
    if not verilator:
        raise RuntimeError("verilator is required")
    command = [verilator, "--cc", "--exe", "--build", "-j", "4",
               "-Wno-fatal", "-Wno-BADVLTPRAGMA", "-CFLAGS", "-std=c++17 -O2",
               "--top-module", "tb_ddr3_fb", "--Mdir", str(output / "obj"),
               str(output / "tb_ddr3_audio.v"),
               str(source / "targets/mister/ddr3_fb.sv"),
               str(source / "targets/mister/mister_audio_output.v"),
               str(source / "common/sync_fifo.v"),
               str(output / "tb_ddr3_audio_main.cpp")]
    with (output / "build.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([str(output / "obj/Vtb_ddr3_fb")],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / "test.log").write_text(result.stdout)
    print(result.stdout, end="")
    result.check_returncode()


if __name__ == "__main__":
    main()
