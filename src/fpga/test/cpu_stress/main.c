#include "vectors.h"
#include "f2i_vectors.h"
volatile unsigned traps;
volatile unsigned scratch[16384];
static void puts_uart(const char *s) {
    while (*s) {
        while (!(*(volatile unsigned *)0x4f000000u & 2)) {}
        *(volatile unsigned *)0x4f000004u = (unsigned char)*s++;
    }
}
static void fail(void) {
    puts_uart("FAIL CPU stress\n");
    for (;;) {}
}
static void hex(unsigned v) {
    char text[10];
    for (unsigned i=0;i<8;++i) text[i]="0123456789abcdef"[(v>>(28-i*4))&15];
    text[8]=' ';text[9]=0;puts_uart(text);
}
#define CVT(OP, RM) __asm__ volatile("csrwi fflags,0; " OP " %0,%2," RM "; csrr %1,fflags" \
                                   : "=r"(result), "=r"(flags) : "f"(x.f) : "memory")
#define MODES(OP) switch(v[1]) {case 0:CVT(OP,"rne");break;case 1:CVT(OP,"rtz");break; \
    case 2:CVT(OP,"rdn");break;case 3:CVT(OP,"rup");break;default:CVT(OP,"rmm");break;}
static void f2i_ranges(void) {
    for (unsigned i=0;i<sizeof(f2i_vectors)/sizeof(f2i_vectors[0]);++i) {
        const unsigned *v=f2i_vectors[i];
        union {unsigned u;float f;} x={v[0]};
        unsigned result,flags;
        if (v[2]) {MODES("fcvt.wu.s")} else {MODES("fcvt.w.s")}
        if (result!=v[3] || flags!=v[4]) {
            puts_uart("F2I FAIL: case,input,mode,unsigned,result,expected,flags,expected\n");
            hex(i);hex(v[0]);hex(v[1]);hex(v[2]);hex(result);hex(v[3]);hex(flags);hex(v[4]);
            fail();
        }
    }
}
int main(void) {
    f2i_ranges();
    for (unsigned round=0; round<4; ++round) {
        for (unsigned i=0; i<1024; ++i) {
            const unsigned *v=vectors[i];
            unsigned r, t;
            __asm__ volatile("mul %0,%2,%3; divu %1,%2,%3; add %0,%0,%1"
                             : "=&r"(r), "=&r"(t) : "r"(v[0]), "r"(v[1]));
            if (r!=v[2]) fail();
            union {unsigned u; float f;} x={v[3]},y={v[4]},z;
            __asm__ volatile("fadd.s %0,%1,%2; fmul.s %0,%0,%2; fsub.s %0,%0,%1; fdiv.s %0,%0,%2"
                             : "=&f"(z.f) : "f"(x.f), "f"(y.f));
            if (z.u!=v[5]) fail();
            __asm__ volatile("fcvt.w.s %0,%2,rtz; add %0,%0,%3; sw %0,0(%1)"
                             : "=&r"(r) : "r"(&scratch[i]), "f"(x.f), "r"(i) : "memory");
            if (scratch[i]!=v[6]+i) fail();
            unsigned old;
            __asm__ volatile("amoadd.w %0,%2,(%1)" : "=&r"(old)
                             : "r"(&scratch[i]), "r"(1) : "memory");
            if (old!=v[6]+i || scratch[i]!=old+1) fail();
            // Unpredictable branch direction and stores after trap return.
            if (v[0]&1) scratch[i]^=v[1]; else scratch[i]+=v[1];
            unsigned expected=(v[0]&1)?((old+1)^v[1]):(old+1+v[1]);
            __asm__ volatile("ecall" ::: "memory");
            if (scratch[i]!=expected || traps!=round*1024+i+1) fail();
        }
    }
    for (unsigned i=0;i<16384;++i) scratch[i]=i*0x10204081u;
    __asm__ volatile("fence rw,rw" ::: "memory");
    for (unsigned i=16384;i--;) if (scratch[i]!=i*0x10204081u) fail();
    puts_uart("CPU stress PASS: integer, FPU, atomics, traps, cache. HAL init\n");
    return 0;
}
