// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
// AXI address/data channels may complete in either order. Exercise both
// target-port implementations with independent stalls and check every beat.
#ifdef TEST_PER_ONLY
#include "Vcpu_target_port_per.h"
using Model = Vcpu_target_port_per;
#else
#include "Vcpu_target_port.h"
using Model = Vcpu_target_port;
#endif
#include <verilated.h>
#include <cstdint>
#include <cstdio>

static void tick(Model &m) {
    m.clk = 0; m.eval();
    m.clk = 1; m.eval();
    m.clk = 0; m.eval();
}

static bool run(bool cached, int words, int aw_delay, int w_delay) {
    Model m;
    m.reset_n = 0;
    m.per_rd_select = m.per_wr_select = 0;
    m.per_arvalid = m.per_awvalid = m.per_wvalid = 0;
    m.m_arready = m.m_rvalid = m.m_awready = m.m_wready = m.m_bvalid = 0;
    m.per_rready = m.per_bready = 1;
#ifndef TEST_PER_ONLY
    m.i_rd_select = m.mem_rd_select = m.mem_wr_select = 0;
    m.i_arvalid = m.mem_arvalid = m.mem_awvalid = m.mem_wvalid = 0;
    m.i_rready = m.mem_rready = m.mem_bready = 1;
#endif
    for (int i = 0; i < 5; ++i) tick(m);
    m.reset_n = 1;
    int sent = 0, received = 0, addresses = 0, responses = 0;
    bool offered = true, replied = false, valid = true;
    for (int cycle = 0; cycle < 250; ++cycle) {
        const uint32_t value = 0x12340000u + sent;
        m.per_wr_select = offered && !cached;
        m.per_awvalid = offered && !cached;
        m.per_awaddr = 0x30000100;
        m.per_awlen = words - 1;
        m.per_awburst = 1;
        m.per_wvalid = !cached && sent < words;
        m.per_wdata = value;
        m.per_wstrb = 15;
        m.per_wlast = sent == words - 1;
#ifndef TEST_PER_ONLY
        m.mem_wr_select = offered && cached;
        m.mem_awvalid = offered && cached;
        m.mem_awaddr = 0x30000100;
        m.mem_awlen = words - 1;
        m.mem_awid = 2;
        m.mem_awburst = 1;
        m.mem_wvalid = cached && sent < words;
        m.mem_wdata = value;
        m.mem_wstrb = 15;
        m.mem_wlast = sent == words - 1;
#endif
        m.m_awready = cycle >= aw_delay;
        m.m_wready = cycle >= w_delay && (cycle % 7 != 4);
        m.m_bvalid = !replied && addresses == 1 && received == words;
        m.m_bresp = 0;
        m.eval();
        bool aw = m.per_awvalid && m.per_awready_contrib;
        bool w = m.per_wvalid && m.per_wready_contrib;
        bool b = m.per_bvalid_contrib;
#ifndef TEST_PER_ONLY
        if (cached) {
            aw = m.mem_awvalid && m.mem_awready_contrib;
            w = m.mem_wvalid && m.mem_wready_contrib;
            b = m.mem_bvalid_contrib;
            if (b && m.mem_bid_contrib != 2) valid = false;
        }
#endif
        if (m.m_awvalid && m.m_awready) {
            ++addresses;
            if (m.m_awaddr != 0x30000100u || m.m_awlen != words - 1)
                valid = false;
        }
        if (m.m_wvalid && m.m_wready) {
            if (m.m_wdata != 0x12340000u + received || m.m_wstrb != 15 ||
                m.m_wlast != (received == words - 1)) valid = false;
            ++received;
        }
        if (m.m_bvalid) replied = true; // downstream B has no ready port
        if (b) ++responses;
        tick(m);
        if (aw) offered = false;
        if (w) ++sent;
        if (responses) {
            // Catch a lingering AWVALID after an early W completion.
            for (int i = 0; i < 3; ++i) {
                m.m_bvalid = 0;
                m.eval();
                if (m.m_awvalid) valid = false;
                tick(m);
            }
            break;
        }
    }
    valid &= sent == words && received == words && addresses == 1 && responses == 1;
    std::printf("%s %s words=%d AW-delay=%d W-delay=%d sent=%d received=%d AW=%d B=%d\n",
                valid ? "PASS" : "FAIL", cached ? "cached" : "peripheral",
                words, aw_delay, w_delay, sent, received, addresses, responses);
    return valid;
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    int failed = 0;
    for (int cached = 0; cached <
#ifdef TEST_PER_ONLY
         1;
#else
         2;
#endif
         ++cached)
        for (int words : {1, 2, 4, 16})
            for (int aw_delay : {0, 2, 8, 40})
                for (int w_delay : {0, 3, 45})
                    failed += !run(cached, words, aw_delay, w_delay);
    std::printf("CPU target port: %d failed\n", failed);
    return failed != 0;
}
