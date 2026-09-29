/* Real CPU cache traffic: different-set 4 KiB aliases and same-set evictions. */
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
static void fail(unsigned phase, unsigned expected, unsigned actual) {
    put("CACHE FAIL "); hex(phase); hex(expected); hex(actual); put("\n");
    for (;;) {}
}
static unsigned now(void) { return *(volatile unsigned *)0x40000004u; }
static void flush(uintptr_t p) {
    __asm__ volatile(".insn i 0x0f, 2, x0, %0, 2" :: "r"(p) : "memory");
}
static unsigned initial(unsigned page, unsigned word) {
    return (page * 37u + word) ^ 0xa55a1020u;
}
static unsigned value(unsigned page, unsigned round) {
    return (page * 0x10204081u) ^ (round * 0x10201u);
}
int main(void) {
    static const unsigned strides[] = {64, 4096, 65536};
    for (unsigned kind = 0; kind < 3; ++kind) {
        unsigned stride = strides[kind], hash = 2166136261u;
        for (unsigned page = 0; page < 32; ++page) {
            uintptr_t addr = 0x11000000u + page * stride;
            flush(addr);
            volatile unsigned *p = (volatile unsigned *)(addr + 0x40000000u);
            for (unsigned w = 0; w < 16; ++w) p[w] = initial(page, w);
        }
        __asm__ volatile("fence rw,rw" ::: "memory");
        unsigned start = now();
        for (unsigned round = 0; round < 64; ++round) {
            unsigned word = round & 15;
            for (unsigned page = 0; page < 32; ++page) {
                unsigned next = (page + 1) & 31;
                volatile unsigned *p = (volatile unsigned *)(0x11000000u + page * stride);
                volatile unsigned *q = (volatile unsigned *)(0x11000000u + next * stride);
                p[word] = value(page, round);
                unsigned got = q[word];
                unsigned expected = next == 0 ? value(next, round)
                                    : round < 16 ? initial(next, word) : value(next, round - 16);
                if (got != expected) fail(1, expected, got);
                hash = (hash ^ got) * 16777619u;
            }
        }
        unsigned cycles = now() - start;
        for (unsigned page = 0; page < 32; ++page) {
            uintptr_t addr = 0x11000000u + page * stride;
            volatile unsigned *p = (volatile unsigned *)addr;
            for (unsigned w = 0; w < 16; ++w) {
                unsigned expected = value(page, 48 + w), old;
                __asm__ volatile("amoadd.w %0,%2,(%1)" : "=&r"(old)
                                 : "r"(&p[w]), "r"(7) : "memory");
                if (old != expected || p[w] != expected + 7) fail(2, expected, old);
            }
            flush(addr);
            /* A same-master uncached read waits for the flushed writeback. */
            volatile unsigned *uncached = (volatile unsigned *)(addr + 0x40000000u);
            for (unsigned w = 0; w < 16; ++w) {
                unsigned expected = value(page, 48 + w) + 7, got = uncached[w];
                if (got != expected) fail(3, expected, got);
            }
        }
        put("CACHE "); hex(stride); hex(cycles); hex(hash); put("\n");
    }
    put("CACHE PASS HAL init\n");
    return 0;
}
