/* One GPU frame plus one CPU frame, using two immutable DMA source buffers.
 * Publication may split a frame at capacity or an explicit texture fence.
 * Ordinary renderer kicks do not force small synchronous submissions. */
static uint32_t list_storage[2][SM64_LIST_WORDS] __attribute__((aligned(64)));
static unsigned list_index, list_old_fb, list_retired_epoch;
static int list_started;
uint32_t sm64_list_submissions, sm64_list_words, sm64_list_peak;
uint32_t sm64_list_capacity_flushes, sm64_list_texture_waits;
uint32_t sm64_list_dma_polls;

static void list_acquire(void) {
    if (!g_flip_pending) return;
    gpu_wait_flip_fence(g_flip_token);
    g_draw_idx = of_video_acquire_next(g_draw_idx, g_flip_token);
    g_draw_fb = (uint32_t)(uintptr_t)of_video_buffer_addr(g_draw_idx);
    g_flip_pending = 0;
    list_retired_epoch = g_tex_epoch - 1u;
    if (g_st_cache_valid && g_st_cache.fb_base == list_old_fb)
        g_st_cache.fb_base = g_draw_fb;
    if (!g_fb_active) {
        g_fb_active = 1;
        of_video_set_display_mode(OF_DISPLAY_FRAMEBUFFER);
    }
}

static void list_relocate(uint32_t *p, unsigned count) {
    for (unsigned i=0; i<count;) {
        unsigned n=p[i]&0xffffffu, op=p[i]>>24;
        if (n>=count-i) __builtin_trap();
        switch(op) {
        case GPU_CMD_SET_FB: case GPU_CMD_SET_TRI_STATE:
            if (!n) __builtin_trap();
            if (p[i+1]==list_old_fb) p[i+1]=g_draw_fb;
            break;
        case GPU_CMD_CLEAR_RECT: {
            if (!n) __builtin_trap();
            unsigned offset=p[i+1]-list_old_fb;
            if (offset<(unsigned)FB_STRIDE*SCR_H*g_fb_bpp)
                p[i+1]=g_draw_fb+offset;
            break;
        }
        case GPU_CMD_FENCE: case GPU_CMD_FLIP: case GPU_CMD_SET_TEXTURE:
        case GPU_CMD_DRAW_VERT_TRI: case GPU_CMD_DRAW_VERT_TRI_RGB:
        case GPU_CMD_SET_OBJECT_STATE: case GPU_CMD_LOAD_VERTS:
        case GPU_CMD_DRAW_INDEXED_TRI: case GPU_CMD_LOAD_VERT_CLIP: break;
        default: __builtin_trap();
        }
        i+=n+1;
    }
}

static void list_flush(int force) {
    if (!list_started || !_gpu_cmd_words) return;
    if (!force && !_gpu_unflushed_sync) return;
    list_acquire();
    unsigned count=_gpu_cmd_words;
    list_relocate(_gpu_batch_buf,count);
    /* Previous descriptor must have consumed its entire source before the
     * next buffer can be recycled. Its already-buffered commands may render
     * concurrently. Every new frame additionally retires the preceding flip. */
    unsigned spins=0;
    while (GPU_STATUS & GPU_STATUS_DMA_BUSY) {
        sm64_list_dma_polls++;
        sm64_audio_service();
        if (++spins==50000000u) __builtin_trap();
    }
    _gpu_flush_cmd_cache_range(_gpu_batch_buf,count*4u);
    _gpu_drain_cmd_writeback(count*4u);
    GPU_CTRL=GPU_CTRL_DMA_RING_SELECT;
    if (GPU_STATUS & GPU_STATUS_CPU_RING_MODE) __builtin_trap();
    GPU_DMA_SRC=(uint32_t)(uintptr_t)_gpu_batch_buf;
    GPU_DMA_LEN=0x80000000u|count; /* private streaming extension */
    GPU_DMA_KICK=1;
    sm64_list_submissions++;
    sm64_list_words+=count;
    if (count>sm64_list_peak) sm64_list_peak=count;
    _gpu_cmd_words=0;
    _gpu_unflushed_sync=0;
    list_index^=1u;
    _gpu_batch_buf=list_storage[list_index];
}

static void list_begin(void) {
    if (_gpu_cmd_words) __builtin_trap();
    list_started=1;
    list_old_fb=g_draw_fb;
    _gpu_batch_buf=list_storage[list_index];
    if (g_tex_epoch==UINT32_MAX) {
        list_acquire();
        for(unsigned i=0;i<MAX_TEX;i++)
            g_tex[i].slot_epoch[0]=g_tex[i].slot_epoch[1]=0;
        list_retired_epoch=g_tex_epoch=0;
    }
    ++g_tex_epoch;
#ifdef SM64_LIST_EARLY_CLEAR
    if (g_flip_pending && of_gpu_fence_reached(g_flip_token)) list_acquire();
#endif
}

static void list_texture(unsigned epoch) {
    /* A prior frame can still own this texture while the next list is built.
     * Current-frame reuse retains the renderer's existing finish barrier. */
    if (epoch && epoch!=g_tex_epoch && (int32_t)(epoch-list_retired_epoch)>0) {
        sm64_list_texture_waits++;
        list_acquire();
    }
}
