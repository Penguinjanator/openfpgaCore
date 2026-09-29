// SPDX-License-Identifier: Apache-2.0
// fcvt.s.w / fcvt.s.wu results and fflags against an exact Python reference
// in all rounding modes, then dependency/hazard sequences around the
// conversion: dependent FP use, load->convert, back-to-back conversions,
// conversions behind a long fdiv, and across a trap.  Prints a hash of the
// hazard results so different CPU builds can be compared.
#include "i2f_vectors.h"
volatile unsigned traps;
volatile unsigned scratch[64];
static void puts_uart(const char *s) {
    while (*s) {
        while (!(*(volatile unsigned *)0x4f000000u & 2)) {}
        *(volatile unsigned *)0x4f000004u = (unsigned char)*s++;
    }
}
static void hex(unsigned v) {
    char text[10];
    for (unsigned i=0;i<8;++i) text[i]="0123456789abcdef"[(v>>(28-i*4))&15];
    text[8]=' ';text[9]=0;puts_uart(text);
}
static void fail(const char *what, unsigned i, unsigned a, unsigned b) {
    puts_uart("FAIL I2F ");puts_uart(what);puts_uart(": ");hex(i);hex(a);hex(b);puts_uart("\n");
    for (;;) {}
}
#define CVT(OP, RM) __asm__ volatile("csrwi fflags,0; " OP " %0,%2," RM "; csrr %1,fflags" \
                                   : "=f"(r.f), "=r"(flags) : "r"(v[0]) : "memory")
#define MODES(OP) switch(v[1]) {case 0:CVT(OP,"rne");break;case 1:CVT(OP,"rtz");break; \
    case 2:CVT(OP,"rdn");break;case 3:CVT(OP,"rup");break;default:CVT(OP,"rmm");break;}
// The Pocket/MiSTer CPUs are generated with --fpu-ignore-subnormal, which in
// VexiiRiscv's packer also drops the rounding-inexact flag for every FP op
// (FpuPackerPlugin: `if(!ignoreSubnormal) when(roundAdjusted =/= 0) nx`).
// Values are still correctly rounded.  The vectors carry the IEEE NX bit; set
// EXPECT_NX=1 for a core that raises it.
#ifndef EXPECT_NX
#define EXPECT_NX 0
#endif
static unsigned hash = 2166136261u;
static void mix(unsigned v) { hash = (hash ^ v) * 16777619u; }
int main(void) {
    const unsigned n = sizeof(i2f_vectors)/sizeof(i2f_vectors[0]);
    for (unsigned i=0;i<n;++i) {
        const unsigned *v=i2f_vectors[i];
        union {unsigned u; float f;} r;
        unsigned flags;
        if (v[2]) {MODES("fcvt.s.wu")} else {MODES("fcvt.s.w")}
        if (r.u!=v[3]) fail("value",i,r.u,v[3]);
        if (flags!=(EXPECT_NX ? v[4] : 0u)) fail("fflags",i,flags,v[4]);
    }
    // Hazards: signed RNE vectors only (every 10th row is signed/RNE).
    for (unsigned k=0;k<n;k+=10) {
        const unsigned *v=i2f_vectors[k];
        union {unsigned u; float f;} a,b,c;
        unsigned x,y;
        // Dependent add right behind the conversion (2x is exact).
        __asm__ volatile("fcvt.s.w %0,%2; fadd.s %1,%0,%0" : "=&f"(a.f), "=f"(b.f) : "r"(v[0]));
        if (a.u!=v[3]) fail("dep-src",k,a.u,v[3]);
        if (v[3] && b.u!=v[3]+(1u<<23)) fail("dep-add",k,b.u,v[3]);
        mix(b.u);
        // Load -> convert -> move back to the integer file.
        scratch[k&63]=v[0];
        __asm__ volatile("lw %1,0(%2); fcvt.s.w %0,%1; fmv.x.w %1,%0"
                         : "=&f"(a.f), "=&r"(x) : "r"(&scratch[k&63]) : "memory");
        if (x!=v[3]) fail("load-cvt",k,x,v[3]);
        // Back-to-back conversions, ALU-produced source, then all three used.
        __asm__ volatile("addi %3,%4,1; fcvt.s.w %0,%4; fcvt.s.w %1,%3; fcvt.s.w %2,%4; fsub.s %0,%0,%2"
                         : "=&f"(a.f), "=&f"(b.f), "=&f"(c.f), "=&r"(y) : "r"(v[0]));
        if (a.u!=0) fail("b2b",k,a.u,0);
        mix(b.u);
        // Conversion queued behind a long fdiv; both results consumed.
        union {unsigned u; float f;} d={0x40490fdbu}, e={0x3f800000u + (k<<3)};
        __asm__ volatile("fdiv.s %0,%2,%3; fcvt.s.w %1,%4; fadd.s %0,%0,%1"
                         : "=&f"(a.f), "=&f"(b.f) : "f"(d.f), "f"(e.f), "r"(v[0]));
        if (b.u!=v[3]) fail("div-cvt",k,b.u,v[3]);
        mix(a.u);
        // Conversion in flight across a trap.
        unsigned before=traps;
        __asm__ volatile("fcvt.s.w %0,%1; ecall" : "=f"(a.f) : "r"(v[0]) : "memory");
        if (a.u!=v[3] || traps!=before+1) fail("trap",k,a.u,v[3]);
    }
    puts_uart("I2F hash ");hex(hash);puts_uart("\n");
    puts_uart("CPU i2f PASS: fcvt.s.w[u] all modes, flags and hazards. HAL init\n");
    return 0;
}
