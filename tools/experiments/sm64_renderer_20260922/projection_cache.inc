/* Exact memo of the existing quantized GPU-compatible projection. */
#define PROJECT_CACHE_BITS 7
struct gpu_projection_entry {
    uint32_t cx, cy, cw, generation;
    int16_t x, y;
};
static struct gpu_projection_entry g_project_cache[1u << PROJECT_CACHE_BITS];
static uint32_t g_project_generation = 1;
static int32_t g_project_cx = SCR_W * 8, g_project_cy = SCR_H * 8;
static int32_t g_project_hw = SCR_W / 2, g_project_hh = SCR_H * 8;

static void gpu_project_viewport_changed(void) {
    g_project_cx = (int32_t)lrintf(g_cx) * 16;
    g_project_cy = (int32_t)lrintf(g_cy * 16.0f);
    g_project_hw = (int32_t)lrintf(g_hw);
    g_project_hh = (int32_t)lrintf(g_hh * 16.0f);
    if (++g_project_generation == 0) {
        memset(g_project_cache, 0, sizeof(g_project_cache));
        g_project_generation = 1;
    }
}

static uint32_t gpu_float_bits(float f) {
    uint32_t bits;
    memcpy(&bits, &f, sizeof(bits));
    return bits;
}
