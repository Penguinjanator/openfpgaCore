// SPDX-License-Identifier: Apache-2.0
// A single in-flight mixer with variable completion latency. Every numbered
// stereo sample must reach the output once, in order, at the DAC cadence.
#include "Vmister_audio_output.h"
#include <verilated.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>

static int failures;

static void run_case(bool is90, int pattern) {
    Vmister_audio_output dut;
    dut.reset_n = 0;
    dut.mixer_enable = 0;
    dut.clk_is90 = is90;
    dut.sample_wr = 0;
    dut.sample_data = 0;
    auto tick = [&]() {
        dut.clk = 0; dut.eval();
        dut.clk = 1; dut.eval();
    };
    for (int i = 0; i < 10; ++i) tick();
    dut.reset_n = 1;
    dut.mixer_enable = 1;
    int work = 0, next_id = 1, last_id = 0, last_cycle = 0;
    int bad_order = 0, bad_cadence = 0, minimum = 1000000, maximum = 0;
    uint32_t rng = 17;
    double period = 4294967296.0 / (is90 ? 2290649 : 2061584);
    for (int cycle = 0; cycle < 3000000 && last_id < 1000; ++cycle) {
        dut.clk = 0; dut.eval();
        bool start = !work && dut.fifo_level < 768;
        tick();
        dut.sample_wr = 0;
        if (work && --work == 0) {
            dut.sample_wr = 1;
            dut.sample_data = (uint32_t(next_id) << 16) | uint16_t(~next_id);
            ++next_id;
        } else if (start) {
            rng = rng * 1664525u + 1013904223u;
            work = pattern == 0 ? 400 :
                   pattern == 1 ? (next_id & 1 ? 250 : 1750) :
                   pattern == 2 ? (100 + rng % 1600) :
                   pattern == 3 ? (next_id % 97 == 0 ? 6000 : 400) :
                   pattern == 4 ? (next_id == 300 ? 120000 : 400) : 1;
        }
        if (dut.audio_l != last_id) {
            int id = dut.audio_l;
            if (id != last_id + 1 || dut.audio_r != uint16_t(~id)) ++bad_order;
            if (last_id > 20) {
                int interval = cycle - last_cycle;
                minimum = std::min(minimum, interval);
                maximum = std::max(maximum, interval);
                // Pattern 4 deliberately exceeds the finite buffer. Recovery
                // may hold the last sample, but must never lose/reorder data.
                if (pattern != 4 && (interval < std::floor(period) ||
                                     interval > std::ceil(period))) ++bad_cadence;
            }
            last_id = id;
            last_cycle = cycle;
        }
    }
    bool ok = last_id == 1000 && !bad_order && !bad_cadence;
    if (!ok) ++failures;
    printf("%s %d MHz pattern=%d: samples=%d intervals=%d..%d "
           "cadence_errors=%d order_errors=%d\n", ok ? "PASS" : "FAIL",
           is90 ? 90 : 100, pattern, last_id, minimum, maximum, bad_cadence, bad_order);
    dut.mixer_enable = 0;
    dut.sample_wr = 0;
    tick();
    if (dut.audio_l || dut.audio_r) {
        ++failures;
        puts("FAIL disable must clear buffered output");
    }
}

static void test_clock_switch_reset() {
    Vmister_audio_output dut;
    dut.clk_is90 = 0;
    dut.reset_n = 0;
    dut.mixer_enable = 1;
    dut.sample_wr = 0;
    auto tick = [&]() {
        dut.clk = 0; dut.eval();
        dut.clk = 1; dut.eval();
    };
    tick();
    dut.reset_n = 1;
    dut.sample_wr = 1;
    dut.sample_data = 0x12345678;
    for (int i = 0; i < 8; ++i) tick();
    dut.sample_wr = 0;
    // MiSTer holds this domain in reset during its 100 -> 90 MHz fallback.
    dut.reset_n = 0;
    dut.clk_is90 = 1;
    tick();
    bool ok = !dut.audio_l && !dut.audio_r;
    dut.reset_n = 1;
    for (int i = 1; i <= 8; ++i) {
        dut.sample_wr = 1;
        dut.sample_data = (uint32_t(i) << 16) | uint16_t(~i);
        tick();
    }
    dut.sample_wr = 0;
    int previous = 0, previous_cycle = 0;
    for (int c = 0; c < 6000; ++c) {
        tick();
        if (dut.audio_l != previous) {
            int id = dut.audio_l;
            ok &= id == previous + 1 && dut.audio_r == uint16_t(~id);
            if (previous) ok &= c - previous_cycle == 1875;
            previous = id;
            previous_cycle = c;
        }
    }
    ok &= previous == 3;
    if (!ok) ++failures;
    printf("%s clock switch reset flushes queued audio and selects 90 MHz cadence\n",
           ok ? "PASS" : "FAIL");
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    for (bool is90 : {false, true})
        for (int pattern = 0; pattern < 6; ++pattern) run_case(is90, pattern);
    test_clock_switch_reset();
    printf("%d failed cases\n", failures);
    return failures ? 1 : 0;
}
