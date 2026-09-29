/* Exercise SDK initialization and transport selection with modeled MMIO. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static uint32_t regs[16];
static int capability, refuse;
static volatile uint32_t *reg(unsigned offset);
#include "of_gpu_test.h"
static struct of_capabilities caps;
const struct of_capabilities *_of_caps_ptr = &caps;
static volatile uint32_t *reg(unsigned offset) {
  unsigned ctrl = regs[0];
  regs[0] = 0;
  if (ctrl & 6)
    regs[5] =
        GPU_STATUS_RING_EMPTY | (capability ? GPU_STATUS_CPU_RING_CAP : 0);
  if ((ctrl & GPU_CTRL_CPU_RING_SELECT) && capability && !refuse)
    regs[5] |= GPU_STATUS_CPU_RING_MODE;
  return &regs[offset / 4];
}
static void check(int supported, int rejected, uint32_t completed) {
  capability = supported;
  refuse = rejected;
  caps.gpu_base = 0x80000000u;
  caps.sdram_base = 1;
  caps.sdram_size = UINT32_MAX - 1;
  _gpu_cpu_ring = 1;
  _gpu_cmd_words = 17;
  _gpu_unflushed_sync = 1;
  _gpu_state_valid = UINT32_MAX;
  _gpu_span_hdr_valid = 1;
  _gpu_batch_inflight_mask = 3;
  regs[6] = completed;
  of_gpu_init();
  assert(_gpu_fence_next == completed + 1u);
  assert(!of_gpu_fence_reached(_gpu_fence_next));
  assert(_gpu_cpu_ring == (supported && !rejected));
  assert(!_gpu_cmd_words && !_gpu_batch_inflight_mask && !_gpu_unflushed_sync);
  assert(!_gpu_state_valid && !_gpu_span_hdr_valid && !_gpu_wrptr &&
         !_gpu_known_rdptr);
  assert(_gpu_batch_buf == &_gpu_batch_storage[0][0]);
  assert(GPU_PALOOKUP_BASE == (uintptr_t)_gpu_palookup_storage);
}
int main(void) {
  check(0, 0, 0);
  check(1, 0, 1);
  check(1, 1, 77);
  check(0, 0, 0x7fffffff);
  check(1, 0, UINT32_MAX);
  _gpu_cpu_ring = 0;
  _gpu_cmd_words = 1;
  assert(!of_gpu_use_cpu_ring());
  _gpu_cmd_words = 0;
  _gpu_batch_inflight_mask = 1;
  assert(!of_gpu_use_cpu_ring());
  _gpu_batch_inflight_mask = 0;
  regs[5] |= GPU_STATUS_DMA_BUSY;
  assert(!of_gpu_use_cpu_ring());
  regs[5] &= ~GPU_STATUS_DMA_BUSY;
  assert(of_gpu_use_cpu_ring());
  puts("PASS automatic CPU ring, older-core DMA fallback, refusal, "
       "reinitialization and pending submissions");
}
