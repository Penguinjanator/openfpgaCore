// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
#include "Vaxi_sdram_slave.h"
#include <verilated.h>
#include <cstdint>
#include <cstdio>
#include <initializer_list>

static uint32_t pattern(uint32_t address) {
    return (address * 0x9e3779b9u) ^ 0x71a539cdu;
}

static bool run(unsigned words, unsigned stall) {
    Vaxi_sdram_slave d;
    d.reset_n = 0;
    d.s_axi_arvalid = d.s_axi_awvalid = d.s_axi_wvalid = 0;
    d.s_axi_rready = 0;
    d.s_axi_bready = 1;
    d.s_axi_wcont = 0;
    d.sdram_busy = d.sdram_accepted = d.sdram_rdata_valid = 0;
    d.sdram_wr_done = d.sdram_wr_data_next = 0;
    for (int i = 0; i < 4; ++i) {
        d.clk = 0; d.eval(); d.clk = 1; d.eval();
    }
    d.reset_n = 1;
    const uint32_t base = 0x12340;
    d.s_axi_araddr = base * 4;
    d.s_axi_arlen = words - 1;
    d.s_axi_arvalid = 1;
    unsigned received = 0, remaining = 0, delay = 0, issued = 0;
    uint32_t native_address = 0, held_data = 0;
    bool ar_done = false, held = false, held_last = false;
    bool good = true;
    for (unsigned cycle = 0; cycle < 10000; ++cycle) {
        d.clk = 0;
        d.s_axi_rready = cycle >= stall && (cycle % 23 < 17);
        d.sdram_rdata_valid = remaining && !delay;
        d.sdram_rdata = pattern(native_address);
        d.sdram_busy = remaining != 0;
        d.sdram_accepted = 0;
        d.eval();
        const bool accept = !remaining && d.sdram_rd;
        const unsigned native_words = d.sdram_burst_len + 1;
        const uint32_t address = d.sdram_addr;
        d.sdram_accepted = accept;
        d.eval();
        if (held && (!d.s_axi_rvalid || d.s_axi_rdata != held_data
                    || bool(d.s_axi_rlast) != held_last)) good = false;
        held = d.s_axi_rvalid && !d.s_axi_rready;
        held_data = d.s_axi_rdata;
        held_last = d.s_axi_rlast;
        const bool ar_fire = d.s_axi_arvalid && d.s_axi_arready;
        if (d.s_axi_rvalid && d.s_axi_rready) {
            if (d.s_axi_rdata != pattern(base + received)
                || d.s_axi_rresp != 0
                || bool(d.s_axi_rlast) != (received + 1 == words)) good = false;
            ++received;
        }
        const bool native_data = d.sdram_rdata_valid;
        d.clk = 1; d.eval();
        if (ar_fire) { ar_done = true; d.s_axi_arvalid = 0; }
        if (accept) {
            if (address != base + issued || issued + native_words > words) good = false;
            issued += native_words;
            remaining = native_words;
            native_address = address;
            delay = 3;
        } else if (delay) {
            --delay;
        } else if (native_data) {
            --remaining;
            ++native_address;
        }
        if (ar_done && received >= words) break;
    }
    good = good && received == words && issued == words;
    std::printf("%s words=%u stall=%u received=%u issued=%u\n",
                good ? "PASS" : "FAIL", words, stall, received, issued);
    d.final();
    return good;
}

// Offer a second write while the first B response is held. AW and W are
// independent; every accepted transaction must eventually yield one B beat.
static bool write_backpressure(unsigned w_delay) {
    Vaxi_sdram_slave d;
    d.reset_n = 0;
    d.s_axi_arvalid = d.s_axi_awvalid = d.s_axi_wvalid = 0;
    d.s_axi_rready = 1;
    d.s_axi_bready = 0;
    d.s_axi_wcont = 0;
    d.sdram_busy = d.sdram_accepted = d.sdram_rdata_valid = 0;
    d.sdram_wr_done = d.sdram_wr_data_next = 0;
    for (int i = 0; i < 4; ++i) {
        d.clk = 0; d.eval(); d.clk = 1; d.eval();
    }
    d.reset_n = 1;
    unsigned aw = 0, w = 0, b = 0, native = 0, busy = 0;
    bool good = true, held = false;
    unsigned held_resp = 0;
    for (unsigned cycle = 0; cycle < 300; ++cycle) {
        d.clk = 0;
        d.s_axi_awvalid = aw < 2;
        d.s_axi_awaddr = 0x4000 + 4 * aw;
        d.s_axi_awlen = 0;
        d.s_axi_wvalid = w < 2 && cycle >= w_delay;
        d.s_axi_wdata = pattern(w);
        d.s_axi_wstrb = 15;
        d.s_axi_wlast = 1;
        d.s_axi_bready = cycle >= 100;
        d.sdram_busy = busy != 0;
        d.sdram_wr_done = busy == 1;
        d.sdram_accepted = 0;
        d.eval();
        const bool accept = !busy && d.sdram_wr;
        d.sdram_accepted = accept;
        d.eval();
        if (held && (!d.s_axi_bvalid || d.s_axi_bresp != held_resp)) good = false;
        held = d.s_axi_bvalid && !d.s_axi_bready;
        held_resp = d.s_axi_bresp;
        if (d.s_axi_awvalid && d.s_axi_awready) ++aw;
        if (d.s_axi_wvalid && d.s_axi_wready) ++w;
        if (d.s_axi_bvalid && d.s_axi_bready) { ++b; good &= d.s_axi_bresp == 0; }
        if (accept) {
            good &= d.sdram_addr == 0x1000 + native && d.sdram_wdata == pattern(native);
            good &= d.sdram_wstrb == 15 && d.sdram_burst_wr_len == 0;
            ++native;
        }
        d.clk = 1; d.eval();
        if (accept) busy = 5;
        else if (busy) --busy;
    }
    good &= aw == 2 && w == 2 && b == 2 && native == 2;
    std::printf("%s B backpressure w_delay=%u aw=%u w=%u b=%u native=%u\n",
                good ? "PASS" : "FAIL", w_delay, aw, w, b, native);
    d.final();
    return good;
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    unsigned failures = 0;
    for (unsigned words : {1u, 2u, 4u, 16u, 17u, 32u, 256u})
        for (unsigned stall : {0u, 100u, 333u})
            failures += !run(words, stall);
    for (unsigned delay : {0u, 8u, 40u}) failures += !write_backpressure(delay);
    std::printf("SDRAM response tests: %u failures\n", failures);
    return failures ? 1 : 0;
}
