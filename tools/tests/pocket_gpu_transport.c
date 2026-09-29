#include "of_gpu.h"
#ifndef TRANSPORT_TRIANGLES
#define TRANSPORT_TRIANGLES 0
#endif
void *memset(void *p, int c, size_t n) {
  unsigned char *s = p;
  while (n--)
    *s++ = c;
  return p;
}
void *memcpy(void *p, const void *q, size_t n) {
  unsigned char *s = p;
  const unsigned char *t = q;
  while (n--)
    *s++ = *t++;
  return p;
}
volatile unsigned traps;
static const struct of_capabilities caps = {.gpu_base = 0x4a000000,
                                            .sdram_base = 0x10000000,
                                            .sdram_size = 0x4000000,
                                            .sdram_uncached_base = 0x50000000,
                                            .platform_id = OF_PLATFORM_POCKET,
                                            .hw_features =
                                                TRANSPORT_TRIANGLES
                                                ? (OF_HW_GPU_VERT_TRI | OF_HW_GPU_VCOLOR)
                                                : OF_HW_GPU_COLUMN_LIST};
const struct of_capabilities *_of_caps_ptr = &caps;
static void put(const char *s) {
  while (*s) {
    while (!(*(volatile unsigned *)0x4f000000 & 2)) {
    }
    *(volatile unsigned *)0x4f000004 = *s++;
  }
}
static void hex(unsigned v) {
  char b[10];
  for (unsigned i = 0; i < 8; i++)
    b[i] = "0123456789abcdef"[(v >> (28 - i * 4)) & 15];
  b[8] = ' ';
  b[9] = 0;
  put(b);
}
static unsigned now(void) { return *(volatile unsigned *)0x40000004; }
static void die(void) {
  put("TRANSPORT FAIL\n");
  for (;;) {
  }
}
static void emit(unsigned kind, unsigned count) {
  if (!kind) {
    _gpu_cmd_header(0xfe, count);
    uint32_t *p = _gpu_ring_claim();
    for (unsigned i = 0; i < count; i++)
      p[i] = i;
    _gpu_ring_commit(count);
  } else {
#if TRANSPORT_TRIANGLES
    of_gpu_tri_state_t st = {0};
    st.fb_base = 0x11000000;
    st.fb_major_step = 640;
    st.fb_minor_step = 2;
    st.tex_addr = 0x11100000;
    st.tex_width = 1;
    st.tex_w_mask = st.tex_h_mask = 1;
    st.flags = OF_GPU_SPAN_TRUECOLOR;
    st.clip_x1 = 320;
    st.clip_y1 = 200;
    st.subpix_y = 1;
    of_gpu_set_tri_state(&st);
    const int32_t uv[3] = {0, 0, 0};
    const int32_t zi[3] = {65536, 65536, 65536};
    const int32_t depth[3] = {0, 0, 0};
    for (unsigned tile = 0; tile < 40; tile++) {
      uint16_t color = tile % 3 == 0 ? 0xf800 : tile % 3 == 1 ? 0x07e0 : 0x001f;
      const uint16_t rgb[3] = {color, color, color};
      int16_t x[3] = {tile * 128, (tile + 1) * 128, tile * 128};
      int16_t y[3] = {0, 0, count * 16};
      of_gpu_draw_vert_tri_rgb(x, y, uv, uv, zi, rgb, 0, depth, NULL);
      x[0] = x[1]; y[1] = y[2];
      of_gpu_draw_vert_tri_rgb(x, y, uv, uv, zi, rgb, 0, depth, NULL);
    }
#else
    of_gpu_column_list_group_t g = {0};
    g.lane_count = 4;
    g.tex_width = 1;
    g.tex_h_mask = 255;
    g.fb_step = 320;
    for (unsigned k = 0; k < 4; k++) {
      g.fb_addr[k] = 0x11000000 + k;
      g.tex_addr[k] = 0x11100000;
      g.count[k] = count;
      g.tstep[k] = 65536;
    }
    for (unsigned x = 0; x < 80; x++) {
      for (unsigned k = 0; k < 4; k++)
        g.fb_addr[k] = 0x11000000 + 4 * x + k;
      of_gpu_draw_column_list(&g);
    }
#endif
  }
}
static unsigned check(unsigned kind, unsigned n) {
  if (!kind)
    return 0;
  unsigned h = 2166136261u;
  volatile uint32_t *fb = (volatile uint32_t *)0x51000000;
  for (unsigned y = 0; y < 200; y++)
    for (unsigned x = 0; x < (TRANSPORT_TRIANGLES ? 160 : 80); x++) {
#if TRANSPORT_TRIANGLES
      unsigned tile = x / 4;
      unsigned color = tile % 3 == 0 ? 0xf800 : tile % 3 == 1 ? 0x07e0 : 0x001f;
      unsigned expected_word = y < n ? color * 0x00010001u : 0x6d6d6d6d;
      unsigned got = fb[y * 160 + x];
#else
      unsigned expected = y < n ? ((y * 37 + 11) & 255) : 0x6d;
      unsigned got = fb[y * 80 + x];
      unsigned expected_word = expected * 0x01010101u;
#endif
      if (got != expected_word)
        die();
      for (unsigned k = 0; k < 4; k++)
        h = (h ^ ((got >> (8 * k)) & 255)) * 16777619u;
    }
  return h;
}
int main(void) {
  volatile unsigned char *tex = (volatile unsigned char *)0x51100000;
  for (unsigned y = 0; y < 256; y++)
    tex[y] = y * 37 + 11;
#if TRANSPORT_TRIANGLES
  *(volatile uint32_t *)tex = 0xffffffffu;
#endif
  /* Exercise upload tails before timing: exact publication counts and fence
   * completion must survive every small length and cache-line boundary. */
  static const unsigned tails[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
                                    13, 14, 15, 16, 17, 31, 32, 33, 63, 64,
                                    65, 127, 128, 129, 1023, 1024, 1025, 4000};
  for (unsigned i = 0; i < sizeof(tails) / sizeof(tails[0]); i++) {
    of_gpu_init();
    emit(0, tails[i]);
    unsigned expected = _gpu_cmd_words;
    unsigned token = of_gpu_fence();
    expected += 2;
    of_gpu_kick();
    of_gpu_wait(token);
    if (GPU_RING_WRPTR != expected * 4 || GPU_RING_RDPTR != expected * 4) {
      put("BOUNDARY ");
      hex(tails[i]);
      hex(expected * 4);
      hex(GPU_RING_WRPTR);
      hex(GPU_RING_RDPTR);
      put("\n");
      die();
    }
  }
  put("TRANSPORT boundary checks PASS\n");
  for (unsigned kind = 0; kind < 2; kind++)
    for (unsigned si = 0; si < 4; si++)
      for (unsigned mode = FIRST_MODE; mode < 2; mode++) {
        unsigned n = kind ? (si == 0   ? 1
                             : si == 1 ? 16
                             : si == 2 ? 80
                                       : 200)
                          : (si == 0   ? 16
                             : si == 1 ? 128
                             : si == 2 ? 1024
                                       : 4000);
        of_gpu_init();
        if (mode) {
          if (!of_gpu_use_cpu_ring())
            die();
        } else {
          GPU_CTRL = GPU_CTRL_DMA_RING_SELECT;
          _gpu_cpu_ring = 0;
        }
        volatile unsigned char *fb = (volatile unsigned char *)0x51000000;
        if (kind)
          for (unsigned i = 0; i < (TRANSPORT_TRIANGLES ? 32000 : 16000); i++)
            ((volatile uint32_t *)fb)[i] = 0x6d6d6d6d;
        emit(kind, n);
        of_gpu_finish(); // warm caches and command buffers
        unsigned start = now();
        for (unsigned r = 0; r < 4; r++) {
          emit(kind, n);
          of_gpu_finish();
        }
        unsigned cycles = now() - start;
        unsigned hash = check(kind, n);
        put("TRANSPORT ");
        hex(kind);
        hex(n);
        hex(mode);
        hex(cycles);
        hex(hash);
        put("\n");
      }
  put("TRANSPORT PASS HAL init\n");
  return 0;
}
