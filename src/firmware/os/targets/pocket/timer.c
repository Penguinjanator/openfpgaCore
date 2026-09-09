//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------

/*
 * openfpgaOS Timer HAL Implementation
 */

#include "timer.h"
#include "file.h"
#include "regs.h"

void of_timer_init(void) {
    /* No initialization required */
}

uint32_t of_timer_get_us(void) {
    /* Use the clock reported by the core, including the 90 MHz fallback. */
    return (uint32_t)(read_cycles() / (CPU_FREQ_HZ / 1000000));
}

uint32_t of_timer_get_ms(void) {
    return (uint32_t)(read_cycles() / (CPU_FREQ_HZ / 1000));
}

uint32_t of_timer_get_seconds(uint32_t *ns_out) {
    uint64_t cycles = read_cycles();
    uint32_t sec = (uint32_t)(cycles / CPU_FREQ_HZ);
    if (ns_out) {
        uint64_t rem = cycles % CPU_FREQ_HZ;
        *ns_out = (uint32_t)((rem * 1000000000ull) / CPU_FREQ_HZ);
    }
    return sec;
}

void of_timer_delay_us(uint32_t us) {
    uint64_t target = read_cycles() + (uint64_t)us * (CPU_FREQ_HZ / 1000000);

    /* Software mixer retired in hw-mixer v2 phase 5+6 — the busy-wait no
     * longer needs to pump swmixer_tick() during delays.  The hardware
     * mixer keeps producing samples on its own FSM, independent of any
     * CPU-side tick.  Left as a plain spin with a shutdown check so the
     * Pocket can still exit the loop early on a system-reset request. */
    while (read_cycles() < target) {
        of_check_shutdown();
    }
}

void of_timer_delay_ms(uint32_t ms) {
    of_timer_delay_us(ms * 1000);
}
