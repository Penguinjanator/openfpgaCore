/* Drive the real of_video_acquire_next against a modelled GPU flip, display
 * swap slot and vsync IRQ (gpu_core / axi_periph_slave semantics): a slow
 * GPU, back-to-back flips, a paused system menu, a wedged flip and a caller
 * with interrupts off.  check_video_acquire.py substitutes the RV32 asm. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#define read_cycles regs_read_cycles     /* its body reads real MMIO */
#include "regs.h"
#undef read_cycles

/* Capture the addresses that need behaviour, then route every access. */
#undef REG32
#define REG32(addr) ((uintptr_t)(addr))
static const uintptr_t SWAP_CTRL_ADDR = FB_SWAP_CTRL;
static const uintptr_t FENCE_ADDR = GPU_FENCE_REACHED_REG;
static const uintptr_t VSYNC_PENDING_ADDR = VSYNC_IRQ_PENDING;
#undef REG32
static volatile uint32_t *mock_reg(uintptr_t addr);
#define REG32(addr) (*mock_reg((uintptr_t)(addr)))

/* 100 MHz CPU, 60 Hz vblanks, 10 cycles per register access. */
#define VBLANK_CYCLES 1666667ull
#define ACCESS_CYCLES 10ull
#define MS(n) ((uint64_t)(n) * 100000ull)
uint32_t g_cpu_freq_hz = 100000000u;
static uint64_t now, next_vblank = VBLANK_CYCLES;
static uint64_t read_cycles(void) { return now; }

/* Replacements for video.c's asm sites. */
static uint32_t mock_mstatus = 0x8u;                 /* MIE */
static void mock_fence(void) { __atomic_thread_fence(__ATOMIC_SEQ_CST); }
static uint32_t mock_csrrci_mie(void) { uint32_t p = mock_mstatus; mock_mstatus &= ~0x8u; return p; }
static void mock_csrrsi_mie(void) { mock_mstatus |= 0x8u; }

void of_cache_clean_range(void *addr, uint32_t size) { (void)addr; (void)size; }
int  of_analogizer_is_enabled(void) { return 0; }
void of_term_printf(const char *fmt, ...) { (void)fmt; }
void of_term_set_display_mode(int mode) { (void)mode; }

#ifndef VIDEO_SOURCE
#error "VIDEO_SOURCE must name the asm-substituted video.c"
#endif
#include VIDEO_SOURCE

/* Modelled hardware. */
static uint32_t hw_display, hw_ready, hw_pending;   /* display slave swap slot */
static uint32_t fence_value;                         /* GPU_FENCE_REACHED */
static int      flip_queued;                         /* a CMD_FLIP is in the ring */
static uint32_t flip_idx, flip_token;
static uint64_t flip_drained_at;                     /* UINT64_MAX: never drains */
static int      menu_open;                           /* video_frozen */
static uint64_t menu_close_at = UINT64_MAX;
static unsigned cpu_kicks, irqs;
static int      in_irq;
static volatile uint32_t swap_shadow, swap_composed, fence_shadow, zero_reg;
static volatile uint32_t other_regs[256];

static void hw_step(void) {
    now += ACCESS_CYCLES;
    if (swap_shadow != swap_composed) {              /* the CPU wrote FB_SWAP_CTRL */
        hw_ready = (swap_shadow >> 1) & 3u;
        hw_pending = swap_shadow & 1u;
        swap_composed = swap_shadow;
        cpu_kicks++;
    }
    if (menu_open && now >= menu_close_at)
        menu_open = 0;
    /* CMD_FLIP retires once its writes drained and the slot is free. */
    if (flip_queued && now >= flip_drained_at && !hw_pending) {
        hw_ready = flip_idx; hw_pending = 1; fence_value = flip_token; flip_queued = 0;
    }
    while (now >= next_vblank) {
        next_vblank += VBLANK_CYCLES;
        if (menu_open)
            continue;                                /* no consume, no vsync IRQ */
        if (hw_pending) { hw_display = hw_ready; hw_pending = 0; }
        if ((mock_mstatus & 0x8u) && !in_irq) {
            in_irq = 1;
            irqs++;
            uint32_t saved = mock_mstatus;
            mock_mstatus &= ~0x8u;
            of_video_vsync_irq_service();
            mock_mstatus = saved;
            in_irq = 0;
        }
    }
}

static volatile uint32_t *mock_reg(uintptr_t addr) {
    hw_step();
    if (addr == SWAP_CTRL_ADDR) {
        swap_composed = swap_shadow = (hw_display << 1) | hw_pending;
        return &swap_shadow;
    }
    if (addr == FENCE_ADDR) { fence_shadow = fence_value; return &fence_shadow; }
    if (addr == VSYNC_PENDING_ADDR) { zero_reg = 0; return &zero_reg; }
    return &other_regs[(addr >> 2) & 255u];
}

/* Display 0, previous frame fully presented, app drawing into buffer 1. */
static void reset(void) {
    hw_display = 0; hw_ready = 0; hw_pending = 0; flip_queued = 0;
    menu_open = 0; menu_close_at = UINT64_MAX; mock_mstatus = 0x8u;
    buf_display = 0; buf_draw = 1; buf_ready = -1; swap_kicked = 0;
    cpu_kicks = 0;
}

static void queue_flip(uint32_t idx, uint64_t drain_cycles) {
    flip_idx = idx; flip_token++; flip_queued = 1;
    flip_drained_at = drain_cycles == UINT64_MAX ? UINT64_MAX : now + drain_cycles;
}

static int acquire(uint32_t idx, uint64_t *elapsed) {
    uint64_t t0 = now;
    int next = of_video_acquire_next((int)idx, flip_token);
    hw_step();                                       /* observe a trailing write */
    *elapsed = now - t0;
    assert(next >= 0 && next < 3 && (uint32_t)next != idx && next != buf_display);
    return next;
}

int main(void) {
    uint64_t t;

    /* A GPU that drains in 1 ms: no CPU swap. */
    reset(); queue_flip(1, MS(1));
    acquire(1, &t);
    assert(cpu_kicks == 0 && fence_value == flip_token && t >= MS(1) && t < MS(3));

    /* A 60 ms GPU frame (beyond the old 5 ms bound): wait for it, never
     * present the unfinished buffer. */
    reset(); queue_flip(1, MS(60));
    acquire(1, &t);
    assert(cpu_kicks == 0 && fence_value == flip_token && t >= MS(60));

    /* Back-to-back flips: CMD_FLIP holds until vsync consumes the pending
     * swap, so the fence arrives within a frame. */
    reset(); queue_flip(1, MS(1)); acquire(1, &t);
    queue_flip(2, 0);
    acquire(2, &t);
    assert(cpu_kicks == 0 && fence_value == flip_token && t <= VBLANK_CYCLES + MS(1));

    /* A system menu opens with a swap pending: vblanks and swaps freeze and
     * the next CMD_FLIP holds.  Acquire blocks for the whole 2 s menu. */
    reset(); queue_flip(1, MS(1)); acquire(1, &t);
    menu_open = 1; menu_close_at = now + MS(2000);
    unsigned irqs_before = irqs;
    queue_flip(2, MS(1));
    acquire(2, &t);
    assert(cpu_kicks == 0 && fence_value == flip_token && t >= MS(2000));
    assert(irqs - irqs_before <= 2);                 /* none counted while frozen */

    /* A wedged flip: give up after 30 displayed vblanks and queue the swap
     * from the CPU so the app degrades instead of hanging. */
    reset(); queue_flip(1, UINT64_MAX);
    acquire(1, &t);
    assert(cpu_kicks == 1 && hw_pending && hw_ready == 1);
    assert(t >= 29 * VBLANK_CYCLES && t <= 31 * VBLANK_CYCLES);

    /* Interrupts off: vblanks cannot be counted, so keep the short spin. */
    reset(); mock_mstatus = 0; queue_flip(1, MS(60));
    acquire(1, &t);
    assert(cpu_kicks == 1 && t < MS(60));
    reset(); mock_mstatus = 0; queue_flip(1, MS(1));
    acquire(1, &t);
    assert(cpu_kicks == 0 && fence_value == flip_token);

    puts("PASS: acquire waits for slow GPUs and paused menus, degrades only on a wedged flip");
    return 0;
}
