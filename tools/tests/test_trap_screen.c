/* Decode the rendered pixels to verify all crash values without hardware. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../src/firmware/os/kernel/trap_screen.h"

int main(void)
{
    static uint8_t font[2048], pixels[352 * 240];
    /* A synthetic glyph encodes its character in every bitmap row. */
    for (unsigned ch = 0; ch < 256; ++ch)
        memset(font + ch * 8, ch, 8);
    memset(pixels, 0x55, sizeof(pixels));
    trap_screen_report(pixels, 352, font, 2, 0x10412345, 0xffffffff, 0x13ff0010, 0);
    const char *expected[] = {
        "CPU trap", "cause:  00000002", "pc:     10412345",
        "addr:   ffffffff", "sp:     13ff0010", "ra:     00000000"
    };
    for (unsigned row = 0; row < 240; ++row) {
        for (unsigned col = 0; col < 352; ++col) {
            uint8_t actual = pixels[row * 352 + col];
            if (row >= 48 || col >= 320) {
                assert(actual == 0x55); /* Preserve log rows and stride padding. */
            } else {
                const char *line = expected[row / 8];
                unsigned ch = col / 8 < strlen(line) ? (uint8_t)line[col / 8] : ' ';
                assert(actual == ((ch & (0x80u >> (col & 7))) ? 15 : 4));
            }
        }
    }
    puts("PASS: visible trap registers, hexadecimal formatting and framebuffer bounds");
    return 0;
}
