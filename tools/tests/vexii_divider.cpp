#include "Vtb_dividers.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
static Vtb_dividers t;
static uint32_t seed = 0x79b315efu;
static uint64_t cycles2[2] = {}, cycles4[2] = {}, cases[2] = {};
static uint32_t rnd() {
  seed ^= seed << 13;
  seed ^= seed >> 17;
  seed ^= seed << 5;
  return seed;
}
static void step() {
  t.clk = 0;
  t.eval();
  t.clk = 1;
  t.eval();
}
static void check(bool ok, const char *what) {
  if (!ok) {
    std::printf(
        "FAIL %s a=%08x b=%08x norm=%u q2=%08x r2=%08x q4=%08x r4=%08x\n", what,
        t.a, t.b, t.normalized, t.q2, t.r2, t.q4, t.r4);
    std::exit(1);
  }
}
static void one(uint32_t a, uint32_t b, bool normalized) {
  t.a = a;
  t.b = b;
  t.normalized = normalized;
  t.valid = 1;
  t.ready2 = t.ready4 = 0;
  t.eval();
  check(t.accept2 && t.accept4, "ready before command");
  step();
  t.valid = 0;
  uint64_t numerator = normalized ? uint64_t(a) << 26 : a;
  uint32_t q = b ? uint32_t(numerator / b) : UINT32_MAX,
           r = b ? uint32_t(numerator % b) : a;
  unsigned wait = 0, n2 = 0, n4 = 0;
  while (!(t.valid2 && t.valid4) && wait++ < 70) {
    if (!t.valid2)
      ++n2;
    if (!t.valid4)
      ++n4;
    step();
  }
  cycles2[normalized] += n2;
  cycles4[normalized] += n4;
  ++cases[normalized];
  check(t.valid2 && t.valid4, "completion timeout");
  check(t.q2 == q && t.r2 == r && t.q4 == q && t.r4 == r, "quotient/remainder");
  for (unsigned n = rnd() % 5; n--;) {
    step();
    check(t.valid2 && t.valid4 && t.q2 == q && t.q4 == q && t.r2 == r &&
              t.r4 == r,
          "backpressured response stability");
  }
  t.ready2 = t.ready4 = 1;
  step();
  t.ready2 = t.ready4 = 0;
  step();
}
int main() {
  t.reset = 1;
  t.flush = 0;
  t.valid = 0;
  t.ready2 = t.ready4 = 0;
  step();
  step();
  t.reset = 0;
  step();
  const uint32_t e[] = {0,          1,          2,          3,         4,
                        7,          8,          15,         16,        127,
                        128,        255,        256,        65535,     65536,
                        0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff};
  unsigned count = 0;
  for (auto a : e)
    for (auto b : e) {
      one(a, b, false);
      ++count;
    }
  for (unsigned i = 0; i < 100000; ++i) {
    one(rnd(), rnd(), false);
    ++count;
  }
  for (unsigned i = 0; i < 100000; ++i) {
    one(0x800000 | (rnd() & 0x7fffff), 0x800000 | (rnd() & 0x7fffff), true);
    ++count;
  }
  for (auto a :
       {0x800000u, 0x800001u, 0xbfffffu, 0xc00000u, 0xfffffeu, 0xffffffu})
    for (auto b :
         {0x800000u, 0x800001u, 0xbfffffu, 0xc00000u, 0xfffffeu, 0xffffffu}) {
      one(a, b, true);
      ++count;
    }
  for (unsigned i = 0; i < 4096; ++i) {
    t.a = rnd();
    t.b = rnd();
    t.normalized = i & 1;
    t.valid = 1;
    step();
    t.valid = 0;
    for (unsigned n = rnd() % 40; n--;)
      step();
    t.flush = 1;
    step();
    t.flush = 0;
    t.eval();
    check(!t.valid2 && !t.valid4 && t.accept2 && t.accept4,
          "flush cancels busy/completed response");
    one(rnd(), rnd(), false);
  }
  std::printf("PASS %u integer/normalized-mantissa divisions, response stalls, "
              "and 4096 flush/restart cases\n",
              count);
  for (unsigned i = 0; i < 2; ++i)
    std::printf("Mean divider compute cycles (%s): radix2=%.3f radix4=%.3f\n",
                i ? "FP mantissa" : "integer", double(cycles2[i]) / cases[i],
                double(cycles4[i]) / cases[i]);
}
