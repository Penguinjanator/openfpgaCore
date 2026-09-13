// SPDX-License-Identifier: Apache-2.0
// Exercise the production cache block during initialization and warm resets.
#include "Vcache_protocol.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static Vcache_protocol *model;
#define t (*model)
static uint32_t seed = 0x923811a1;
static uint32_t rnd() {
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    return seed;
}
static uint32_t value(uint32_t key) { return (key * 0x9e3779b1u) ^ 0x51ba925a; }
static void tick() {
    t.clk = 0;
    t.eval();
    t.clk = 1;
    t.eval();
}
static void reset(bool cold) {
    t.persp_pss = 0;
    t.reset_n = !cold;
    t.soft_reset = cold ? 0 : 1;
    tick();
    t.reset_n = 1;
    t.soft_reset = 0;
}
int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    model = new Vcache_protocol;
    t.state = 1;
    t.persp_active = 1;
    t.sp_persp_q29_mode = 1;
    reset(true);
    unsigned hits = 0, checks = 0, early = 0, age = 0;
    for (unsigned i = 0; i < 200000; i++) {
        if (i % 257 == 0) {
            reset(i % 514 == 0);
            age = 0;
        }
        uint32_t key = (i % 3 == 0) ? 0x00304080u : rnd();
        t.persp_zinv_abs_r = key;
        t.persp_pss = 2;
        tick();
        age++;
        if (t.hit) {
            if (age <= 128) {
                fprintf(stderr, "Uninitialized cache hit\n");
                return 1;
            }
            if (t.value != value(key)) {
                fprintf(stderr, "Incorrect cache value\n");
                return 1;
            }
            hits++;
        }
        checks++;
        if (age <= 128)
            early++;
        t.persp_pss = 15;
        t.dsp_p = uint64_t(value(key)) << 16;
        tick();
        age++;
        t.persp_pss = 2;
        tick();
        age++;
        checks++;
        if (age <= 128)
            early++;
        if (t.hit) {
            if (age <= 128) {
                fprintf(stderr, "Uninitialized read/fill hit\n");
                return 1;
            }
            if (t.value != value(key)) {
                fprintf(stderr, "Read/fill mismatch\n");
                return 1;
            }
            hits++;
        }
    }
    printf("PASS %u lookups, %u during reset walk, %u exact hits\n", checks, early, hits);
    delete model;
    return hits > 10000 ? 0 : 1;
}
