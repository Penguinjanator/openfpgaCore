/* A blocked GPU must let main-thread services run without early completion. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static uint32_t regs[256], calls, release_after, status_mask, release_rdptr;
static uint32_t release_fence;
static volatile uint32_t *reg(unsigned offset) { return &regs[offset / 4]; }
static void service(void);
#define OF_GPU_WAIT_HOOK() service()
#include "of_gpu_test.h"

static void service(void) {
    if (++calls == release_after) {
        regs[5] &= ~status_mask;
        regs[4] = release_rdptr;
        regs[6] = release_fence;
    }
}

static void blocked(uint32_t status) {
    calls = 0;
    release_after = 7;
    status_mask = status;
    regs[5] = status;
}

int main(void) {
    blocked(GPU_STATUS_DMA_BUSY);
    _gpu_batch_inflight_mask = 3;
    _gpu_wait_dma_idle_debug();
    assert(calls == 7 && !_gpu_batch_inflight_mask);
    blocked(GPU_STATUS_DMA_DESC_FULL);
    _gpu_batch_inflight_mask = 3;
    _gpu_wait_dma_desc_slot_debug();
    assert(calls == 7 && _gpu_batch_inflight_mask == 3);
    blocked(GPU_STATUS_TRANSLUC_BUSY);
    _gpu_wait_transluc_idle();
    assert(calls == 7);

    blocked(0);
    _gpu_wrptr = 0;
    regs[4] = 4; /* Full ring: keep the reserved empty word. */
    release_rdptr = 36;
    assert(!of_gpu_try_reserve_bytes(32, 0) && calls == 0);
    assert(!of_gpu_try_reserve_bytes(32, 3) && calls == 3);
    calls = 0;
    assert(of_gpu_try_reserve_bytes(32, 7) && calls == 7);
    calls = 0;
    assert(of_gpu_try_reserve_bytes(32, 0) && calls == 0);
    assert(!of_gpu_try_reserve_bytes(OF_GPU_RING_SIZE, 7) && calls == 0);

    blocked(0);
    regs[6] = 40;
    release_fence = 41;
    of_gpu_wait(41);
    assert(calls == 7);
    calls = 0;
    of_gpu_wait(41);
    assert(calls == 0);
    regs[6] = UINT32_MAX;
    release_fence = 0;
    of_gpu_wait(0);
    assert(calls == 7);
    puts("PASS GPU wait servicing: DMA, descriptors, translucency, ring bounds, "
         "fence completion and wrap; ready paths do not call the hook");
}
