#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include "audio_clock.h"
#include "pc/audio/audio_api.h"

extern void sm64_audio_service(void);
extern sm64_audio_clock sm64_audio_deadlines;
static uint32_t now, commits, last, max_gap, same_time;
static int reenter;
static struct AudioAPI dummy;
struct AudioAPI *audio_api = &dummy;
unsigned char configEnableSound = 1;
int32_t gSamplesPerFrameTarget = 368;
unsigned of_time_us(void) { return now; }
void gfx_start_frame(void) {}
void gfx_end_frame(void) {}
void game_loop_one_iteration(void) {}
void create_next_audio_buffer(int16_t *scratch, uint32_t samples) {
    assert(samples == 368 || samples == 544);
    scratch[samples * 2 - 1] = 123;
    if (commits) {
        uint32_t gap = now - last;
        if (gap > max_gap) max_gap = gap;
        if (!gap) same_time++;
    }
    commits++; last = now;
    if (reenter) sm64_audio_service();
}
static void reset(uint32_t t) {
    sm64_audio_deadlines = (sm64_audio_clock){0};
    now = t; commits = last = max_gap = same_time = 0;
    configEnableSound = 1; audio_api = &dummy; reenter = 0;
}
int main(void) {
    reset(0);
    /* One hour: integer rounding must not accumulate phase error. */
    for (uint32_t t = 0; t < 3600000000u; t += 1000) {
        now = t; sm64_audio_service();
    }
    assert(commits == 216000);
    assert(sm64_audio_deadlines.due == 3600000000u);
    assert(sm64_audio_deadlines.max_late_us <= 667);
    assert(max_gap == 17000 && !same_time);
    printf("1ms service: ticks=%u max_gap_us=%u max_lateness_us=%u\n",
           commits, max_gap, sm64_audio_deadlines.max_late_us);

    reset(UINT32_MAX - 50000u);
    uint32_t start = now;
    for (uint32_t t = 0; t < 1000000u; t += 250) {
        now = start + t; sm64_audio_service();
    }
    assert(commits == 60 && sm64_audio_deadlines.due == start + 1000000u);
    assert(!sm64_audio_deadlines.rebases);
    reset(7); sm64_audio_service();
    assert(commits == 1); sm64_audio_service(); assert(commits == 1);
    now += 3000000; sm64_audio_service();
    assert(commits == 2 && sm64_audio_deadlines.rebases == 1);
    configEnableSound = 0; now += 100000; sm64_audio_service();
    assert(commits == 2 && !sm64_audio_deadlines.started);
    configEnableSound = 1; sm64_audio_service(); assert(commits == 3);
    reset(0); reenter = 1; sm64_audio_service(); assert(commits == 1);
    now += 200000; sm64_audio_service(); assert(commits == 5);
    /* Work per call is bounded even when the caller is very late. */
    now += 1000000; sm64_audio_service(); assert(commits == 6);
    reset(0); audio_api = NULL; sm64_audio_service(); assert(!commits);
    audio_api = &dummy; gSamplesPerFrameTarget = 10000;
    sm64_audio_service(); assert(commits == 1);
    puts("audio clock/service: PASS (cadence, drift, wrap, pause, disable, reentry, bounded catch-up, sample clamp)");
}
