#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define GPU_CMD_SET_FB 0x23
#define GPU_CMD_CLEAR_RECT 0x11
#define GPU_CMD_SET_TRI_STATE 0x4a
#define GPU_CMD_FENCE 2
#define GPU_CMD_FLIP 0x42
#define GPU_CMD_SET_TEXTURE 0x20
#define GPU_CMD_DRAW_VERT_TRI 0x4b
#define GPU_CMD_DRAW_VERT_TRI_RGB 0x4e
#define GPU_CMD_SET_OBJECT_STATE 0x50
#define GPU_CMD_LOAD_VERTS 0x53
#define GPU_CMD_DRAW_INDEXED_TRI 0x54
#define GPU_CMD_LOAD_VERT_CLIP 0x56
#define OF_GPU_COMMAND_STREAM_BATCH_WORDS 31u
#define OF_DISPLAY_FRAMEBUFFER 1
#define FB_STRIDE 320
#define SCR_H 240
static int g_fb_bpp = 2;
#define PROF_ACQ_BEGIN() ((void)0)
#define PROF_ACQ_END() ((void)0)
static int sm64_preparing, g_flip_pending, g_draw_idx, g_fb_active;
static uint32_t g_flip_token, g_draw_fb, g_tex_epoch;
static uint32_t _gpu_cmd_words, _gpu_wrptr, _gpu_unflushed_sync;
static uint32_t _gpu_ring_mask = 16383, _gpu_batch_index, _gpu_state_valid;
static int _gpu_cpu_ring = 1, g_st_cache_valid;
static struct { uint32_t fb_base; } g_st_cache;
static uint32_t normal[4096], *_gpu_batch_buf = normal;
static uint32_t published[32768], npublished, waits, batches;
static int ready;
static int of_gpu_fence_reached(uint32_t token) { (void)token; return ready; }
static void gpu_wait_flip_fence(uint32_t token) { assert(token == 7); waits++; ready = 1; }
static int of_video_acquire_next(int idx, uint32_t token) {
    assert(idx == 1 && token == 7 && ready); return 2;
}
static void *of_video_buffer_addr(int idx) { assert(idx == 2); return (void *)(uintptr_t)0x10200000; }
static void of_video_set_display_mode(int mode) { assert(mode == 1); }
static void _gpu_select_batch_buffer(uint32_t idx) { _gpu_batch_index = idx; _gpu_batch_buf = normal; }
static void sm64_audio_service(void) {}
static void of_gpu_submit_command_stream_batch(const uint32_t *p, int n) {
    assert(!sm64_preparing && ready && n > 0 && n <= 31);
    memcpy(published + npublished, p, (size_t)n * 4);
    npublished += (uint32_t)n; batches++;
    _gpu_wrptr = (_gpu_wrptr + (uint32_t)n * 4) & _gpu_ring_mask;
}
#include "prepare.inc"
static void reset(void) {
    sm64_preparing = 0; prep_relocating = 0; prep_retired_epoch = 1;
    g_flip_pending = 1; g_draw_idx = 1; g_flip_token = 7;
    g_draw_fb = 0x10100000; g_tex_epoch = 3; ready = 0;
    _gpu_cmd_words = 0; _gpu_wrptr = 16380; _gpu_batch_buf = normal;
    waits = batches = npublished = 0; _gpu_cpu_ring = 1;
    g_st_cache_valid = 1; g_st_cache.fb_base = g_draw_fb;
}
static void put(uint32_t w) {
    _gpu_batch_buf[_gpu_cmd_words++] = w;
    _gpu_wrptr = (_gpu_wrptr + 4) & _gpu_ring_mask;
}
int main(void) {
    reset(); gpu_prepare_begin(); assert(sm64_preparing && !waits);
    put(0x11000003); put(g_draw_fb); put(0x028000f0); put(0x02800000);
    put(0x11000003); put(0x12000000); put(0x028000f0); put(0x02800000);
    for (int k = 0; k < 30; k++) { put(0x54000001); put(0x1234); }
    uint32_t end = _gpu_wrptr;
    gpu_prepare_flush(0); assert(sm64_preparing && !npublished);
    gpu_prepare_flush(1);
    assert(!sm64_preparing && waits == 1 && npublished == 68 && batches == 3);
    assert(published[1] == 0x10200000 && published[5] == 0x12000000);
    assert(_gpu_wrptr == end && g_st_cache.fb_base == g_draw_fb);
    /* A command whose local state was formed before an overflow-triggered
     * acquire must also be relocated when its normal batch is published. */
    uint32_t late[] = {0x4a000011, 0x10100000, 0, 0, 0x10100000, 0, 0, 0,
                       0, 0, 0, 0, 0x12000000, 0, 0, 0, 0, 0};
    gpu_prepare_publish(late, 18);
    assert(late[1] == 0x10200000 && late[4] == 0x10100000 && late[12] == 0x12000000);
    /* Partial byte-uniform fill_rect uses a destination inside the color
     * surface. Match the destination field/range, not other payload words. */
    uint32_t subrect[] = {0x11000003, 0x10100000 + (37 * 320 + 19) * 2,
                         0x00080003, 0x028000ff};
    gpu_prepare_publish(subrect, 4);
    assert(subrect[1] == 0x10200000 + (37 * 320 + 19) * 2);
    for (g_fb_bpp = 1; g_fb_bpp <= 2; g_fb_bpp++) {
        uint32_t size = FB_STRIDE * SCR_H * (uint32_t)g_fb_bpp;
        uint32_t edge[] = {0x11000003, 0x10100000 + size - 1, 0x00010001, 0};
        gpu_prepare_publish(edge, 4);
        assert(edge[1] == 0x10200000 + size - 1);
        edge[1] = 0x10100000 + size;
        gpu_prepare_publish(edge, 4);
        assert(edge[1] == 0x10100000 + size);
        edge[1] = 0x10100000 - 1;
        gpu_prepare_publish(edge, 4);
        assert(edge[1] == 0x10100000 - 1);
    }
    g_fb_bpp = 2;
    reset(); gpu_prepare_begin(); gpu_prepare_texture(0); gpu_prepare_texture(1);
    assert(!waits && sm64_preparing);
    gpu_prepare_texture(2); assert(waits == 1 && !sm64_preparing);
    reset(); gpu_prepare_begin(); gpu_prepare_texture(3);
    assert(waits == 1 && !sm64_preparing);
    reset(); ready = 1; gpu_prepare_begin(); assert(!sm64_preparing && !g_flip_pending);
    reset(); _gpu_cpu_ring = 0; gpu_prepare_begin(); assert(!sm64_preparing && waits == 1);
    puts("frame preparation: PASS (ownership, relocation, partial clears, overflow continuation, shared depth, ring wrap, packet boundaries, texture reuse, DMA fallback)");
}
