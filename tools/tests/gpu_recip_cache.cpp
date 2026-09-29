// SPDX-License-Identifier: Apache-2.0
// Compare the real GPU command/DMA/fragment path with and without reciprocal reuse.
#define main acceptance_main
#include "tb_gpu_acceptance_main.cpp"
#undef main

static uint32_t rng_state = 0x19790912u;
static uint32_t random_word() {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return rng_state;
}

static void initialize() {
    gpu_init();
    sdram_fill(FB_BASE_BYTE, 320u * 200u, SENTINEL_BYTE);
    upload_texture(TEX_BASE_BYTE, make_param_test_texture());
    for (uint32_t i = 0; i < 64u * 256u; ++i)
        sdram_write_byte(PALOOKUP_BASE_BYTE + i, (uint8_t)((i + (i >> 8)) ^ 0x55u));
}

static ParamSpanListWire surface() {
    ParamSpanListWire p{};
    p.fb_base = FB_BASE_BYTE;
    p.fb_major_step = 320; p.fb_minor_step = 1;
    p.tex_addr = TEX_BASE_BYTE;
    p.tex_width = 64; p.tex_w_mask = 63; p.tex_h_mask = 63;
    p.flags = 0x30; p.attr_mode = 3;
    p.attr_origin[0] = 0x01674000;
    p.attr_origin[1] = 0x01256000;
    p.attr_origin[2] = 0x00200000;
    p.attr_du[0] = 0x00018000;
    p.attr_dv[1] = 0x00021000;
    return p;
}

static void finish(const char *kind, unsigned id, uint64_t start) {
    if (!submit_and_wait(4000000)) exit(1);
    uint64_t cycles = sim_time / 2 - start;
    uint64_t hash = UINT64_C(14695981039346656037);
    unsigned changed = 0;
    for (unsigned i = 0; i < 320u * 200u; ++i) {
        uint8_t b = sdram_read_byte(FB_BASE_BYTE + i);
        changed += b != SENTINEL_BYTE;
        hash = (hash ^ b) * UINT64_C(1099511628211);
    }
    if (!changed) { fprintf(stderr, "No pixels drawn\n"); exit(1); }
    printf("RESULT %s %u %llu %016llx %u %u %016llx %u\n", kind, id,
           (unsigned long long)cycles, (unsigned long long)hash,
           tb->dbg_pss_requests, tb->dbg_pss_cache_hits,
           (unsigned long long)tb->dbg_pss_digest, changed);
}

static void locality(bool columns, unsigned length) {
    initialize();
    uint64_t start = sim_time / 2;
    for (unsigned part = 0; part < 8; ++part) {
        auto p = surface();
        p.span_axis = columns;
        p.fb_major_step = columns ? 1 : 320;
        p.fb_minor_step = columns ? 320 : 1;
        p.attr_dv[2] = columns ? 0 : 65536;
        p.attr_du[2] = columns ? 65536 : 0;
        p.light_origin = (int32_t)(part << 16);
        p.attr_origin[0] += (int32_t)(part * 13217);
        std::vector<ParamSpanRecordWire> records;
        for (unsigned line = 0; line < 64; ++line) {
            unsigned offset = (part * 19) % (180 - length);
            records.push_back({(uint16_t)(columns ? line : offset),
                               (uint16_t)(columns ? offset : line), (uint16_t)length});
        }
        emit_param_span_list_raw(p, records);
    }
    finish(columns ? "wall" : "floor", length, start);
}

static void adversarial() {
    initialize();
    const uint32_t edges[] = {0,1,2,127,128,129,65535,65536,65537,
        0x80000000u,0x7fffffffu,0xffffffffu,0xffff0000u,0x200000u};
    for (unsigned test = 0; test < 256; ++test) {
        if (test % 31 == 0) gpu_soft_reset();
        if (test % 97 == 0) initialize();
        auto p = surface();
        p.attr_origin[2] = (int32_t)(test < 14 ? edges[test] : random_word());
        p.attr_du[2] = test % 3 ? 0 : (int32_t)random_word();
        p.attr_dv[2] = test % 5 ? 0 : (int32_t)random_word();
        p.span_axis = test & 1;
        p.q29_attr_shift = test & 31;
        p.attr_origin[0] = (int32_t)random_word();
        p.attr_origin[1] = (int32_t)random_word();
        p.attr_du[0] = (int32_t)random_word();
        p.attr_dv[1] = (int32_t)random_word();
        uint64_t start = sim_time / 2;
        for (unsigned repeat = 0; repeat < 5; ++repeat) {
            // Affine and Q16 work must neither consume nor corrupt Q29 entries.
            // The final two Q29 commands have identical denominators but
            // different origins/light, so hits must retain exact projections.
            p.attr_mode = repeat == 1 ? 0 : repeat == 2 ? 1 : 3;
            p.attr_origin[0] ^= 0x51713219;
            p.light_origin = (int32_t)((test % 64) << 16);
            std::vector<ParamSpanRecordWire> records;
            for (unsigned n = 0; n < 8; ++n)
                records.push_back({(uint16_t)(n * 3), (uint16_t)(test % 120),
                                   (uint16_t)(n ? (1 + test % 33) : 0)});
            emit_param_span_list_raw(p, records);
        }
        finish("edge", test, start);
    }
    // Deliberate index collisions: XORing matching bits in two index folds
    // preserves the hash, but changes the full denominator. Alternate keys
    // and then repeat each to exercise both replacement and reuse.
    for (unsigned test = 0; test < 128; ++test) {
        auto p = surface();
        uint64_t start = sim_time / 2;
        for (unsigned n = 0; n < 8; ++n) {
            p.attr_origin[2] = (int32_t)(0x00300000u ^ (test << 7) ^ test
                                       ^ ((n & 2) ? 0x4080u : 0u));
            emit_param_span_list_raw(p, {{0, 180, 16}, {16, 180, 16}});
        }
        finish("collision", test, start);
    }
}

static void replay_world(const char *path) {
    FILE *input = fopen(path, "rb");
    if (!input) { perror(path); exit(1); }
    auto word = [&]() {
        unsigned char b[4];
        if (fread(b, 4, 1, input) != 1) { fprintf(stderr, "Truncated capture\n"); exit(1); }
        return uint32_t(b[0]) | uint32_t(b[1]) << 8 | uint32_t(b[2]) << 16 | uint32_t(b[3]) << 24;
    };
    initialize();
    // Synthetic texture bytes preserve addressing/cache behavior without
    // copying commercial assets into the RTL test or its output.
    for (unsigned i = 0; i < 256u * 1024u; ++i)
        sdram_write_byte(TEX_BASE_BYTE + i, (uint8_t)((i * 17u) ^ (i >> 7)));
    if (const char *textures = getenv("GPU_TEXTURE_DATA")) {
        FILE *data = fopen(textures, "rb");
        if (!data) { perror(textures); exit(1); }
        while (true) {
            unsigned char header[8];
            size_t n = fread(header, 1, sizeof header, data);
            if (!n && feof(data)) break;
            if (n != sizeof header) { fprintf(stderr, "Truncated texture header\n"); exit(1); }
            auto le32 = [](const unsigned char *p) {
                return uint32_t(p[0]) | uint32_t(p[1]) << 8 |
                       uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
            };
            uint32_t addr = le32(header), size = le32(header + 4);
            if (addr < 0x180000u || addr >= 0x380000u || !size || size > 0x380000u - addr) {
                fprintf(stderr, "Texture outside replay arena\n"); exit(1);
            }
            for (uint32_t i = 0; i < size; ++i) {
                int b = fgetc(data);
                if (b == EOF) { fprintf(stderr, "Truncated texture\n"); exit(1); }
                sdram_write_byte(addr + i, uint8_t(b));
            }
        }
        if (ferror(data) || fclose(data)) exit(1);
    }
    bool frame_open = false;
    unsigned frame = 0;
    uint64_t start = 0;
    struct MemoryCounters {
        uint32_t aw, bursts, beats, write_busy, read_busy, overlap;
    };
    auto memory = [&]() {
        return MemoryCounters{tb->dbg_aw_count, tb->dbg_aw_burst_count,
            tb->dbg_w_beat_cycles, tb->dbg_w_busy_cycles,
            tb->dbg_rd_busy_cycles, tb->dbg_rw_overlap_cycles};
    };
    MemoryCounters first{};
#ifdef GPU_TEST_CACHE_PROFILE
    std::array<uint32_t, 11> cache_first{};
#endif
    auto finish_frame = [&]() {
        finish("world", frame, start);
        auto last = memory();
        printf("MEMORY %u %u %u %u %u %u %u\n", frame,
            last.aw - first.aw, last.bursts - first.bursts,
            last.beats - first.beats, last.write_busy - first.write_busy,
            last.read_busy - first.read_busy, last.overlap - first.overlap);
#ifdef GPU_TEST_CACHE_PROFILE
        printf("CACHE %u", frame);
        for (unsigned i = 0; i < cache_first.size(); ++i)
            printf(" %u", tb->dbg_cache[i] - cache_first[i]);
        printf("\n");
#endif
    };
    while (true) {
        int c = fgetc(input);
        if (c == EOF) break;
        ungetc(c, input);
        uint32_t words = word();
        if (!words) {
            if (frame_open) finish_frame();
            unsigned next_frame = word(); (void)word(); // captured gametic
            // Uncaptured intervening views would change both caches. Start
            // each disjoint sequence cold instead of inventing reuse across
            // the gap. Framebuffer preload lets reset initialization finish
            // outside the measured interval in both configurations.
            if (frame_open && next_frame != frame + 1)
                gpu_init();
            frame = next_frame;
            sdram_fill(FB_BASE_BYTE, 320u * 200u, SENTINEL_BYTE);
            frame_open = true;
            start = sim_time / 2;
            first = memory();
#ifdef GPU_TEST_CACHE_PROFILE
            for (unsigned i = 0; i < cache_first.size(); ++i)
                cache_first[i] = tb->dbg_cache[i];
#endif
        } else {
            if (!frame_open || words < 34 || words > 1024) {
                fprintf(stderr, "Invalid capture command length\n"); exit(1);
            }
            // Keep DMA batches within the physical ring. Fence batch breaks
            // are identical in both runs; CPU/GPU overlap is not modeled.
            if (pending_stream.size() + words + 3 > 2048 && !submit_and_wait(4000000)) exit(1);
            ring_cmd(0x48, words);
            for (unsigned i = 0; i < words; ++i) ring_write(word());
        }
    }
    if (ferror(input) || fclose(input)) exit(1);
    if (!frame_open) { fprintf(stderr, "No captured frames\n"); exit(1); }
    finish_frame();
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    tb = new Vtb_gpu;
    if (const char *path = getenv("GPU_SPAN_STREAM")) {
        replay_world(path);
        delete tb;
        return 0;
    }
    for (unsigned length : {1u, 4u, 16u, 64u, 128u}) {
        locality(false, length);
        locality(true, length);
    }
    adversarial();
    delete tb;
    return 0;
}
