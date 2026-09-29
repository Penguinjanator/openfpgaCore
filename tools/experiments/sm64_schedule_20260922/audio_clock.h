#ifndef SM64_AUDIO_CLOCK_H
#define SM64_AUDIO_CLOCK_H
#include <stdint.h>

/* Absolute 60 Hz deadlines, with no accumulated integer-period drift.
 * Call at non-reentrant service points on the game thread. Times are uint32
 * microseconds; comparisons require successive observations < 2^31 us apart.
 * A long pause rebases instead of issuing historical live voice updates. */
typedef struct {
    uint32_t due, fraction, ticks, rebases, max_late_us;
    uint8_t started;
} sm64_audio_clock;

static inline void sm64_audio_clock_reset(sm64_audio_clock *c) {
    c->started = 0;
    c->fraction = 0;
}

static inline int sm64_audio_clock_take(sm64_audio_clock *c, uint32_t now) {
    if (!c->started) {
        c->started = 1;
        c->due = now;
        c->fraction = 0;
    }
    int32_t late = (int32_t)(now - c->due);
    if (late < 0) return 0;
    if ((uint32_t)late > c->max_late_us) c->max_late_us = (uint32_t)late;
    if (late > 250000) {
        c->rebases++;
        c->due = now;
        c->fraction = 0;
    }
    c->due += 16666u;
    c->fraction += 40u;
    if (c->fraction >= 60u) { c->due++; c->fraction -= 60u; }
    c->ticks++;
    return 1;
}
#endif
