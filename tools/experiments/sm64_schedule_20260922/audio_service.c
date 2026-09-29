#include <stdint.h>
#include "of_timer.h"
#include "pc/audio/audio_api.h"
#include "audio_clock.h"

/* Imported from the existing executable in the overlay build. In a source
 * integration this service belongs in pc_main.c beside its audio_api owner. */
extern struct AudioAPI *audio_api;
extern unsigned char configEnableSound;
extern int32_t gSamplesPerFrameTarget;
extern void create_next_audio_buffer(int16_t *, uint32_t);
extern void gfx_start_frame(void);
extern void gfx_end_frame(void);
extern void game_loop_one_iteration(void);

sm64_audio_clock sm64_audio_deadlines;
static int servicing;

void sm64_audio_service(void) {
    if (servicing) return;
    if (!audio_api || !configEnableSound) {
        sm64_audio_clock_reset(&sm64_audio_deadlines);
        return;
    }
    servicing = 1;
    /* Only the openfpga HW-voice backend: create_next_audio_buffer commits
     * live voice settings. There is no PCM queue to fill ahead of time.
     * Bound catch-up per service point; lateness is retained as telemetry. */
    int16_t scratch[544 * 2];
    for (unsigned n = 0; n < 4; n++) {
        if (!sm64_audio_clock_take(&sm64_audio_deadlines, of_time_us())) break;
        int samples = gSamplesPerFrameTarget;
        if (samples <= 0 || samples > 544) samples = 544;
        create_next_audio_buffer(scratch, (uint32_t)samples);
    }
    servicing = 0;
}

void produce_one_frame(void) {
    sm64_audio_service();
    gfx_start_frame();
    game_loop_one_iteration();
    sm64_audio_service();
    gfx_end_frame();
}
