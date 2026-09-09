/* Minimal crash display: no allocator, terminal state or library calls. */
#ifndef OFOS_TRAP_SCREEN_H
#define OFOS_TRAP_SCREEN_H
#include <stdint.h>

__attribute__((section(".text.boot"), optimize("Os")))
static void trap_screen_report(volatile uint8_t *fb, uint32_t stride,
                               const uint8_t *font, uint32_t cause,
                               uint32_t pc, uint32_t address,
                               uint32_t sp, uint32_t ra)
{
    static const char labels[6][9] __attribute__((section(".rodata.boot"))) = {
        "CPU trap", "cause:  ", "pc:     ",
        "addr:   ", "sp:     ", "ra:     "
    };
    const uint32_t values[6] = {0, cause, pc, address, sp, ra};
    for (unsigned row = 0; row < 6; ++row)
        for (unsigned col = 0; col < 40; ++col) {
            unsigned ch = ' ';
            if (col < 8) ch = (uint8_t)labels[row][col];
            else if (row && col < 16) {
                unsigned digit = (values[row] >> (4 * (15 - col))) & 15;
                ch = digit < 10 ? '0' + digit : 'a' + digit - 10;
            }
            for (unsigned y = 0; y < 8; ++y) {
                unsigned bits = font[ch * 8 + y];
                for (unsigned x = 0; x < 8; ++x)
                    fb[(row * 8 + y) * stride + col * 8 + x] =
                        (bits & (0x80u >> x)) ? 15 : 4;
            }
        }
}
#endif
