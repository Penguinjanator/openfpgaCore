/* SPDX-License-Identifier: Apache-2.0 */
/* Dependent instruction throughput and uncached access cost on the real CPU. */
#include <stdint.h>

volatile unsigned traps;
static void put(const char *s) {
    while (*s) {
        while (!(*(volatile unsigned *)0x4f000000u & 2)) {}
        *(volatile unsigned *)0x4f000004u = (unsigned char)*s++;
    }
}
static void hex(unsigned v) {
    char b[10];
    for (unsigned i = 0; i < 8; ++i) b[i] = "0123456789abcdef"[(v >> (28 - 4*i)) & 15];
    b[8] = ' '; b[9] = 0; put(b);
}
static unsigned now(void) { return *(volatile unsigned *)0x40000004u; }
static void result(unsigned kind, unsigned cycles, unsigned value) {
    put("LATENCY "); hex(kind); hex(1024); hex(cycles); hex(value); put("\n");
}
static void fail(void) { put("LATENCY FAIL\n"); for (;;) {} }

#define FP_TEST(KIND, INSN) do { \
    unsigned value, start = now(); \
    __asm__ volatile( \
        "li t0,0x3f800000\nfmv.w.x fa0,t0\nfmv.w.x fa1,t0\nfmv.w.x fa2,zero\n" \
        "li t0,64\n1:\n.rept 16\n" INSN "\n.endr\n" \
        "addi t0,t0,-1\nbnez t0,1b\nfmv.x.w %0,fa0\n" \
        : "=r"(value) :: "t0", "fa0", "fa1", "fa2", "memory"); \
    unsigned elapsed = now() - start; \
    if (value != 0x3f800000u) fail(); \
    result(KIND, elapsed, value); \
} while (0)

/* Two instructions per access, same address increment cost for all sizes.
 * The reported value includes loop/control overhead and the counter reads. */
#define MEMORY_TEST(KIND, BASE, STRIDE, INSN, EXPECT) do { \
    unsigned value, start = now(); \
    __asm__ volatile( \
        "mv t0,%1\nli t1,64\nli t2,0x5a5a5a5a\n1:\n.rept 16\n" \
        INSN "\naddi t0,t0," STRIDE "\n.endr\n" \
        "addi t1,t1,-1\nbnez t1,1b\nmv %0,t2\n" \
        : "=&r"(value) : "r"((uintptr_t)(BASE)) : "t0", "t1", "t2", "memory"); \
    unsigned elapsed = now() - start; \
    if (value != (EXPECT)) fail(); \
    result(KIND, elapsed, value); \
} while (0)

int main(void) {
    /* Warm the code/cache before retaining the second round. */
    for (unsigned round = 0; round < 2; ++round) {
        put("ROUND "); hex(round); put("\n");
        FP_TEST(0, "fsgnj.s fa0,fa0,fa0");
        FP_TEST(1, "fadd.s fa0,fa0,fa2");
        FP_TEST(2, "fmul.s fa0,fa0,fa1");
        FP_TEST(3, "fmadd.s fa0,fa0,fa1,fa2");
        FP_TEST(4, "fdiv.s fa0,fa0,fa1");
        FP_TEST(5, "fsqrt.s fa0,fa0");
        volatile unsigned *mem = (volatile unsigned *)0x51000000u;
        for (unsigned n = 0; n < 1024; ++n) mem[n] = 0x5a5a5a5au;
        MEMORY_TEST(6, mem, "4", "sw t2,0(t0)", 0x5a5a5a5au);
        MEMORY_TEST(7, mem, "2", "sh t2,0(t0)", 0x5a5a5a5au);
        MEMORY_TEST(8, mem, "1", "sb t2,0(t0)", 0x5a5a5a5au);
        MEMORY_TEST(9, mem, "4", "lw t2,0(t0)", 0x5a5a5a5au);
        for (unsigned n = 0; n < 1024; ++n) if (mem[n] != 0x5a5a5a5au) fail();
        /* Empty commands exercise the real append port, without overflow. */
        volatile unsigned *gpu = (volatile unsigned *)0x4a000000u;
        gpu[0] = 4; gpu[0] = 16;
        MEMORY_TEST(10, &gpu[1], "0", "sw zero,0(t0)", 0x5a5a5a5au);
        if ((gpu[5] & 0x300) != 0x100) fail();
        gpu[0] = 8;
        while (gpu[4] != 4096) {}
        unsigned remaining, start = now();
        __asm__ volatile("li %0,1024\n1:\naddi %0,%0,-1\nbnez %0,1b\n"
                         : "=&r"(remaining) :: "memory");
        unsigned elapsed = now() - start;
        if (remaining != 0) fail();
        result(11, elapsed, remaining);
    }
    put("LATENCY PASS HAL init\n");
    return 0;
}
