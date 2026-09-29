/* Included after gfx_gpu.c's definitions. SDK hooks operate only at complete
 * command boundaries. This prototype has one GPU frame plus one CPU preparation
 * context; it never queues another GPU frame before acquiring a safe target. */
#ifndef SM64_PREP_WORDS
#define SM64_PREP_WORDS 32768u
#endif
static uint32_t prep_storage[SM64_PREP_WORDS];
static uint32_t prep_old_fb;
static uint32_t prep_batch_index;
static uint32_t prep_retired_epoch;
static int prep_relocating;
uint32_t sm64_prepare_frames, sm64_prepare_words, sm64_prepare_peak;
uint32_t sm64_prepare_capacity_flushes, sm64_prepare_texture_waits;

static void gpu_acquire_pending(void) {
    if (!g_flip_pending) return;
    PROF_ACQ_BEGIN();
    gpu_wait_flip_fence(g_flip_token);
    g_draw_idx = of_video_acquire_next(g_draw_idx, g_flip_token);
    PROF_ACQ_END();
    g_draw_fb = (uint32_t)(uintptr_t)of_video_buffer_addr(g_draw_idx);
    g_flip_pending = 0;
    prep_retired_epoch = g_tex_epoch - 1u;
    if (!g_fb_active) {
        g_fb_active = 1;
        of_video_set_display_mode(OF_DISPLAY_FRAMEBUFFER);
    }
}

/* Every address-bearing opcode this SM64 backend can emit is explicit. Reject
 * unsupported streams before publishing any prepared words. These are exact
 * destinations, never arbitrary pointer-looking word replacement. Rect clears
 * can start at a byte offset inside the color target; preserve that offset. */
static void gpu_prepare_publish(uint32_t *words, uint32_t count) {
    if (!prep_relocating) return;
    for (uint32_t i = 0; i < count;) {
        uint32_t n = words[i] & 0xffffffu;
        uint32_t op = words[i] >> 24;
        if (n >= count - i) __builtin_trap();
        switch (op) {
        case GPU_CMD_SET_FB:
        case GPU_CMD_SET_TRI_STATE:
            if (!n) __builtin_trap();
            if (words[i + 1] == prep_old_fb)
                words[i + 1] = g_draw_fb;
            break;
        case GPU_CMD_CLEAR_RECT: { /* color subrect or shared depth */
            if (!n) __builtin_trap();
            uint32_t offset = words[i + 1] - prep_old_fb;
            uint32_t bytes = (uint32_t)FB_STRIDE * SCR_H * (uint32_t)g_fb_bpp;
            if (offset < bytes) words[i + 1] = g_draw_fb + offset;
            break;
        }
        case GPU_CMD_FENCE:
        case GPU_CMD_FLIP:
        case GPU_CMD_SET_TEXTURE:
        case GPU_CMD_DRAW_VERT_TRI:
        case GPU_CMD_DRAW_VERT_TRI_RGB:
        case GPU_CMD_SET_OBJECT_STATE:
        case GPU_CMD_LOAD_VERTS:
        case GPU_CMD_DRAW_INDEXED_TRI:
        case GPU_CMD_LOAD_VERT_CLIP:
            break;
        default: __builtin_trap();
        }
        i += n + 1;
    }
}

static void gpu_prepare_flush(int force) {
    if (!sm64_preparing) return;
#ifdef SM64_PREP_CAPTURE_TEST
    if (!force) return;
#endif
    if (!force && !of_gpu_fence_reached(g_flip_token)) return;
    uint32_t count = _gpu_cmd_words;
    _gpu_cmd_words = 0;
    _gpu_wrptr = (_gpu_wrptr - count * 4u) & _gpu_ring_mask;
    _gpu_unflushed_sync = 0;
    sm64_preparing = 0;
    _gpu_select_batch_buffer(prep_batch_index);
    gpu_acquire_pending();
    prep_relocating = 1;
    gpu_prepare_publish(prep_storage, count);
    sm64_prepare_words += count;
    if (count > sm64_prepare_peak) sm64_prepare_peak = count;
    for (uint32_t i = 0; i < count;) {
        uint32_t begin = i, words = 0;
        while (i < count) {
            uint32_t n = (prep_storage[i] & 0xffffffu) + 1u;
            if (n > OF_GPU_COMMAND_STREAM_BATCH_WORDS) __builtin_trap();
            if (words + n > OF_GPU_COMMAND_STREAM_BATCH_WORDS) break;
            words += n;
            i += n;
        }
        of_gpu_submit_command_stream_batch(prep_storage + begin, (int)words);
        sm64_audio_service();
    }
    if (g_st_cache_valid && g_st_cache.fb_base == prep_old_fb)
        g_st_cache.fb_base = g_draw_fb;
    _gpu_state_valid = 0;
}

static void gpu_prepare_begin(void) {
    prep_relocating = 0;
    if (!g_flip_pending) return;
#ifndef SM64_PREP_CAPTURE_TEST
    if (of_gpu_fence_reached(g_flip_token)) { gpu_acquire_pending(); return; }
#endif
    if (_gpu_cmd_words || !_gpu_cpu_ring) {
        /* Legacy DMA is outside the ownership scope of this experiment. */
        gpu_acquire_pending();
        return;
    }
    sm64_preparing = 1;
    prep_old_fb = g_draw_fb;
    prep_batch_index = _gpu_batch_index;
    _gpu_batch_buf = prep_storage;
    sm64_prepare_frames++;
}

static void gpu_prepare_texture(uint32_t epoch) {
    /* Earlier frames are retired; the immediately preceding frame may still
     * read this slot. A current-frame reuse additionally needs its own finish. */
    if (sm64_preparing && epoch &&
        (int32_t)(epoch - prep_retired_epoch) > 0) {
        sm64_prepare_texture_waits++;
        gpu_prepare_flush(1);
    }
}
