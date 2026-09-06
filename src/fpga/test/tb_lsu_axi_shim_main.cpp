// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
// Stress the production inline shim under independent AW/W backpressure.
#include "Vlsu_axi_shim.h"
#include <verilated.h>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <vector>

struct Write { uint32_t addr, data; uint8_t mask; };
struct Beat { uint32_t data; uint8_t mask; bool last; };
static int failures = 0;
static void check(bool ok, const char* message) {
    if (!ok && failures++ < 12) std::printf("FAIL: %s\n", message);
}
static void tick(Vlsu_axi_shim& t) {
    t.clk = 1; t.eval();
    t.clk = 0; t.eval();
}

static void run(unsigned aw_period, unsigned w_period) {
    Vlsu_axi_shim t;
    t.clk = 0; t.reset = 1;
    t.lsu_cmd_valid = 0; t.lsu_cmd_write = 1;
    t.per_awready_cpu = 0; t.per_wready_cpu = 0; t.per_bvalid_cpu = 0;
    t.per_arready_cpu = 0; t.per_rvalid_cpu = 0; t.per_rlast_cpu = 0;
    t.per_rresp_cpu = 0; t.per_rdata_cpu = 0; t.per_bresp_cpu = 0;
    t.eval(); tick(t); tick(t); t.reset = 0;
    std::vector<Write> commands;
    for (unsigned i = 0; i < 240; ++i) {
        uint32_t address = (i % 40 < 24) ? 0x4a000008u :
                           (i % 40 < 32) ? 0x10010000u : 0x30010000u;
        commands.push_back({address, 0x13579000u ^ (i * 0x10201u),
                           uint8_t((i % 40 < 20) ? 15 : 1u << (i % 4))});
    }
    std::deque<Write> expected;
    std::vector<Beat> beats;
    unsigned sent = 0, received = 0, responses = 0;
    unsigned aw_len = 0, aw_burst = 0, response_delay = 0;
    uint32_t aw_addr = 0;
    bool have_aw = false, have_last = false, response_pending = false;
    bool held_aw = false, held_w = false;
    uint32_t held_addr = 0, held_data = 0;
    unsigned held_len = 0, held_burst = 0, held_mask = 0;
    bool held_last = false;
    for (unsigned cycle = 0; cycle < 50000; ++cycle) {
        t.lsu_cmd_valid = sent < commands.size();
        if (t.lsu_cmd_valid) {
            t.lsu_cmd_addr = commands[sent].addr;
            t.lsu_cmd_data = commands[sent].data;
            t.lsu_cmd_mask = commands[sent].mask;
        }
        t.per_awready_cpu = !have_aw && !response_pending && cycle % aw_period == aw_period - 1;
        t.per_wready_cpu = !have_last && !response_pending && cycle % w_period == w_period - 1;
        t.per_bvalid_cpu = response_pending && response_delay == 0;
        t.eval();
        if (held_aw) check(t.per_awvalid_cpu && t.per_awaddr_cpu == held_addr &&
            t.per_awlen_cpu == held_len && t.per_awburst_cpu == held_burst,
            "AW payload changed under backpressure");
        if (held_w) check(t.per_wvalid_cpu && t.per_wdata_cpu == held_data &&
            t.per_wstrb_cpu == held_mask && t.per_wlast_cpu == held_last,
            "W payload changed under backpressure");
        held_aw = t.per_awvalid_cpu && !t.per_awready_cpu;
        held_addr = t.per_awaddr_cpu; held_len = t.per_awlen_cpu; held_burst = t.per_awburst_cpu;
        held_w = t.per_wvalid_cpu && !t.per_wready_cpu;
        held_data = t.per_wdata_cpu; held_mask = t.per_wstrb_cpu; held_last = t.per_wlast_cpu;
        if (t.lsu_cmd_valid && t.lsu_cmd_ready) expected.push_back(commands[sent++]);
        if (t.lsu_rsp_valid) { ++responses; check(!t.lsu_rsp_error, "posted write response error"); }
        if (t.per_awvalid_cpu && t.per_awready_cpu) {
            have_aw = true; aw_addr = t.per_awaddr_cpu;
            aw_len = t.per_awlen_cpu; aw_burst = t.per_awburst_cpu;
        }
        if (t.per_wvalid_cpu && t.per_wready_cpu) {
            beats.push_back({t.per_wdata_cpu, t.per_wstrb_cpu, bool(t.per_wlast_cpu)});
            have_last = t.per_wlast_cpu;
        }
        bool retired = t.per_bvalid_cpu && t.per_bready_cpu;
        tick(t);
        if (retired) {
            response_pending = have_aw = have_last = false; beats.clear();
        } else if (response_pending && response_delay) {
            --response_delay;
        } else if (have_aw && have_last && !response_pending) {
            check(beats.size() == aw_len + 1, "AWLEN/WLAST disagree");
            for (unsigned j = 0; j < beats.size(); ++j) {
                if (expected.empty()) { check(false, "duplicate write beat"); break; }
                Write e = expected.front(); expected.pop_front();
                check(e.addr == aw_addr + (aw_burst == 0 ? 0 : 4 * j), "write destination changed");
                check(e.data == beats[j].data && e.mask == beats[j].mask, "write data or mask changed");
                ++received;
            }
            response_pending = true; response_delay = 3;
        }
        if (received == commands.size() && !response_pending && expected.empty()) {
            check(responses == sent, "missing posted write response");
            return;
        }
    }
    check(false, "posted write queue failed to drain");
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    for (unsigned aw : {1u, 3u, 8u, 17u, 41u})
        for (unsigned w : {1u, 4u, 11u}) run(aw, w);
    std::printf("LSU shim: 15 stall schedules, 3600 writes, %d failures\n", failures);
    return failures ? 1 : 0;
}
