/* Immediate truecolor fallback. The backend owns SDK state and resolves the
 * material once; the frontend supplies only the inputs that material reads. */
struct gfx_direct_plan {
    unsigned rgb_mask;
    int textured, alpha_input;
};
struct gfx_direct_vertex {
    float cx, cy, cw, w_inv, u, v;
    uint8_t rgb[4][3];
};
const struct gfx_direct_plan *gfx_gpu_direct_begin(void);
void gfx_gpu_direct_triangle(const struct gfx_direct_vertex v[3], uint8_t alpha);
void gfx_gpu_direct_flush(void);
