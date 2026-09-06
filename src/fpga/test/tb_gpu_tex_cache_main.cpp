// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
// Random dual-port cache traffic against an independent backing-memory
// function. Covers conflicts, fill gaps, byte lanes, halfwords, held port-B
// responses, and simultaneous requests/pops without peeking inside the DUT.
#include "Vgpu_tex_cache.h"
#include <verilated.h>
#include <cstdint>
#include <cstdio>
#include <deque>

#ifndef CACHE_SET_BITS
#define CACHE_SET_BITS 4
#endif
static constexpr uint32_t address_mask = (1u << (CACHE_SET_BITS + 7)) - 1;

struct Request { uint32_t address; bool wide; };
static uint32_t random_state = 0x73617264;
static uint32_t random32() {
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}
static uint32_t word(uint32_t address) {
    uint32_t x = (address >> 2) ^ 0x96541e27u;
    x ^= x >> 16; x *= 0x7feb352du;
    x ^= x >> 15; x *= 0x846ca68bu;
    return x ^ (x >> 16);
}
static uint16_t expected(Request r) {
    return r.wide ? ((word(r.address) >> ((r.address & 2) * 8)) & 65535)
                  : ((word(r.address) >> ((r.address & 3) * 8)) & 255);
}
static void tick(Vgpu_tex_cache &m) {
    m.clk = 0; m.eval(); m.clk = 1; m.eval(); m.clk = 0; m.eval();
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    Vgpu_tex_cache m;
    unsigned accepted_a = 0, accepted_b = 0, popped_b = 0, fills = 0;
    int failures = 0;
    for (int epoch = 0; epoch < 4; ++epoch) {
        m.reset_n = 0; m.flush = m.resp_flush_b = m.resp_pop_b = 0;
        m.req_valid = m.req_valid_b = m.axi_arready = m.axi_rvalid = m.axi_rlast = 0;
        for (int i = 0; i < 4; ++i) tick(m);
        m.reset_n = 1;
        Request a{}, next_a{}, next_b{};
        bool a_known = false, a_complete = true;
        std::deque<Request> b;
        int fill_beat = -1, fill_delay = 0;
        uint32_t fill_base = 0;
        for (int cycle = 0; cycle < 60000; ++cycle) {
            const bool sending = cycle < 59000;
            if (!m.req_valid && a_complete && sending && (random32() & 3)) {
                next_a = {random32() & address_mask, bool(random32() & 1)};
                m.req_addr = next_a.address; m.req_wide = next_a.wide; m.req_valid = 1;
            }
            if (!m.req_valid_b && b.size() < 2 && sending && (random32() & 3)) {
                next_b = {random32() & address_mask, bool(random32() & 1)};
                m.req_addr_b = next_b.address; m.req_wide_b = next_b.wide; m.req_valid_b = 1;
            }
            m.resp_pop_b = !b.empty() && (random32() % 5 == 0 || !sending);
            m.axi_arready = fill_beat < 0 && (random32() & 3);
            m.axi_rvalid = fill_beat >= 0 && fill_delay == 0 && (random32() & 3);
            m.axi_rdata = word(fill_base + 4 * (fill_beat < 0 ? 0 : fill_beat));
            m.axi_rlast = m.axi_rvalid && fill_beat == 3;
            m.eval();
            // Pop is only legal for a resolved response.
            m.resp_pop_b &= m.resp_valid_b;
            m.eval();
            if (m.resp_valid && a_known) {
                if (m.resp_data != expected(a)) ++failures;
                a_complete = true;
            }
            if (m.resp_valid_b) {
                if (b.empty() || m.resp_data_b != expected(b.front())) ++failures;
            }
            const bool accept_a = m.req_valid && m.req_ready;
            const bool accept_b = m.req_valid_b && m.req_ready_b;
            if (m.resp_pop_b) { b.pop_front(); ++popped_b; }
            if (m.axi_arvalid && m.axi_arready) {
                if (m.axi_arlen != 3 || (m.axi_araddr & 15)) ++failures;
                fill_beat = 0; fill_base = m.axi_araddr;
                fill_delay = 1 + random32() % 19; ++fills;
            } else if (m.axi_rvalid) {
                if (++fill_beat == 4) fill_beat = -1;
            } else if (fill_delay) --fill_delay;
            tick(m);
            if (accept_a) { a = next_a; a_known = true; a_complete = false;
                            m.req_valid = 0; ++accepted_a; }
            if (accept_b) { b.push_back(next_b); m.req_valid_b = 0; ++accepted_b; }
            if (failures) {
                std::printf("FAIL epoch=%d cycle=%d mismatches=%d\n", epoch, cycle, failures);
                return 1;
            }
        }
        if (!b.empty() || !a_complete || m.req_valid || m.req_valid_b) ++failures;
        // A flush must invalidate both ports and complete without new traffic.
        m.flush = 1; tick(m); m.flush = 0;
        for (int i = 0; i < (1 << CACHE_SET_BITS) + 8; ++i) tick(m);
        if (!m.req_ready || !m.req_ready_b || m.resp_valid || m.resp_valid_b) ++failures;
    }
    if (accepted_a < 1000 || accepted_b != popped_b || popped_b < 1000) ++failures;
    std::printf("Cache SET_BITS=%d: A=%u B=%u pops=%u fills=%u, %d failures\n",
                CACHE_SET_BITS, accepted_a, accepted_b, popped_b, fills, failures);
    return failures != 0;
}
