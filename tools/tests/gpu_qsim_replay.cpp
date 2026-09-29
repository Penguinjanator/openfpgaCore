// SPDX-License-Identifier: Apache-2.0
// Replay qsim captures through the configured GPU; compare full memory and fences.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "Vtb_gpu.h"
#include "Vtb_gpu___024root.h"
#include "verilated.h"

#include "gpuvec.h"
#include <stdexcept>

static Vtb_gpu *tb;
static uint64_t cycles, busy_cycles;

static void tick(int n = 1) {
    for (int i = 0; i < n; i++) {
        tb->clk = 0; tb->eval();
        tb->clk = 1; tb->eval();
        cycles++;
        busy_cycles += tb->busy;
    }
}

static inline uint32_t &sdram_word(uint32_t widx) {
    return tb->rootp->tb_gpu__DOT__sdram_mem[widx & 0xFFFFFF];
}
static uint8_t mem_rd8(uint32_t a) {
    a &= GV_SDRAM_MASK;
    return (uint8_t)(sdram_word(a >> 2) >> ((a & 3) * 8));
}
static void mem_wr8(uint32_t a, uint8_t v) {
    a &= GV_SDRAM_MASK;
    uint32_t &w = sdram_word(a >> 2);
    int sh = (a & 3) * 8;
    w = (w & ~(0xFFu << sh)) | ((uint32_t)v << sh);
}

static void mmio_write(uint32_t reg, uint32_t val) {
    tb->reg_wr = 1; tb->reg_addr = reg; tb->reg_wdata = val;
    tick();
    tb->reg_wr = 0;
}
static uint32_t mmio_read(uint32_t reg) {
    tb->reg_addr = reg; tb->eval();
    return tb->reg_rdata;
}

static bool wait_idle(uint64_t timeout) {
    int quiet = 0;
    for (uint64_t t = 0; t < timeout; t++) {
        tick();
        if (!tb->busy && (mmio_read(5) & 0x8) == 0) {
            if (++quiet >= 64) return true;
        } else {
            quiet = 0;
        }
    }
    return false;
}

static void hard_reset() {
    tb->reset_n = 0; tb->reg_wr = 0; tb->bd_we = 0; tb->slave_swap_pending = 0;
    tick(20);
    tb->reset_n = 1;
    tick(5);
    mmio_write(0, 4);               // ring reset
    mmio_write(0, 1);               // enable (no-op in tb; gpu_enable tied 1)
    mmio_write(12, GV_DEFAULT_PALOOKUP_BASE);
    mmio_write(0, 16);              // select CPU ring transport
    if ((mmio_read(5) & 0x100) == 0) {
        fprintf(stderr, "CPU ring mode not selected\n");
        exit(2);
    }
    mmio_write(10, 1);              // tex flush
    tick(2000);                     // tex cache + recip cache init walks
}

static int run_vector(const char *vec_path, const char *out_path) {
    FILE *f = fopen(vec_path, "rb");
    if (!f) { perror(vec_path); return 2; }
    std::vector<uint8_t> buf;
    {
        fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
        buf.resize((size_t)n);
        if (n && fread(buf.data(), 1, (size_t)n, f) != (size_t)n) { fclose(f); return 2; }
        fclose(f);
    }
    FILE *out = fopen(out_path, "wb");
    if (!out) { perror(out_path); return 2; }

    hard_reset();
    // Zero the whole 64 MB SDRAM model so both sides start identical.
    for (uint32_t i = 0; i < 0x1000000; i++) sdram_word(i) = 0;
    for (uint32_t i = 0; i < 65536; i++) tb->rootp->tb_gpu__DOT__sram_mem[i] = 0;

    const uint64_t start_cycles = cycles, start_busy = busy_cycles;
    size_t pos = 0;
    bool ended = false;
    auto require = [&](size_t n) {
        if (n > buf.size() - pos) throw std::runtime_error("Truncated GPU vector");
    };
    auto rd32 = [&](void) -> uint32_t {
        require(4);
        uint32_t v = (uint32_t)buf[pos] | ((uint32_t)buf[pos+1] << 8)
                   | ((uint32_t)buf[pos+2] << 16) | ((uint32_t)buf[pos+3] << 24);
        pos += 4; return v;
    };
    int rc = 0;
    uint32_t batches = 0;
    while (pos + 4 <= buf.size()) {
        uint32_t tag = rd32();
        if (tag == GV_TAG_MEM) {
            uint32_t addr = rd32(), len = rd32();
            require((size_t(len) + 3) & ~size_t(3));
            for (uint32_t i = 0; i < len; i++) mem_wr8(addr + i, buf[pos + i]);
            pos += (len + 3) & ~3u;
        } else if (tag == GV_TAG_TLUT) {
            require(32768);
            // Upload through the real MMIO window (exercises the SRAM FSM).
            mmio_write(8, 0);
            for (uint32_t i = 0; i < 32768; i += 4) {
                uint32_t w = (uint32_t)buf[pos+i] | ((uint32_t)buf[pos+i+1] << 8)
                           | ((uint32_t)buf[pos+i+2] << 16) | ((uint32_t)buf[pos+i+3] << 24);
                for (int t = 0; t < 1000 && (mmio_read(5) & 8); t++) tick();
                mmio_write(9, w);
            }
            for (int t = 0; t < 1000 && (mmio_read(5) & 8); t++) tick();
            pos += 32768;
        } else if (tag == GV_TAG_PALB) {
            mmio_write(12, rd32());
        } else if (tag == GV_TAG_FLSH) {
            mmio_write(10, 1);
            tick(8);
            if (!wait_idle(1000000)) { fprintf(stderr, "%s: flush idle timeout\n", vec_path); rc = 3; break; }
        } else if (tag == GV_TAG_CMDS) {
            uint32_t n = rd32();
            if (n > 4095) throw std::runtime_error("Oversized GPU batch");
            require(size_t(n) * 4);
            for (uint32_t i = 0; i < n; i++) mmio_write(1, rd32());
            if ((mmio_read(5) & 0x300) != 0x100) {
                fprintf(stderr, "%s: CPU ring overflow/mode lost\n", vec_path);
                rc = 3; break;
            }
            mmio_write(0, 8);   // publish
            batches++;
            if (!wait_idle(50000000ull)) {
                fprintf(stderr, "%s: batch %u hang (state=%u aux=%08x frag=%08x)\n",
                        vec_path, batches, tb->dbg_state, tb->dbg_aux, tb->dbg_frag);
                rc = 4; break;
            }
        } else if (tag == GV_TAG_DUMP) {
            uint32_t addr = rd32(), len = rd32();
            for (uint32_t i = 0; i < len; i++) { uint8_t b = mem_rd8(addr + i); fputc(b, out); }
        } else if (tag == GV_TAG_FENC) {
            uint32_t v = tb->fence_reached;
            fwrite(&v, 4, 1, out);
        } else if (tag == GV_TAG_RAND) {
            uint32_t addr = rd32(), len = rd32(); unsigned st = rd32();
            for (uint32_t i = 0; i < len; i++) mem_wr8(addr + i, (uint8_t)gv_rand_next(&st));
        } else if (tag == GV_TAG_HASH) {
            uint64_t h = 0xcbf29ce484222325ull;
            for (uint32_t i = 0; i < 0x1000000; i++) {
                uint32_t w = sdram_word(i);
                for (int b = 0; b < 4; b++) { h ^= (uint8_t)(w >> (8 * b)); h *= 0x100000001b3ull; }
            }
            fwrite(&h, 8, 1, out);
        } else if (tag == GV_TAG_END) {
            ended = true;
            break;
        } else {
            fprintf(stderr, "%s: bad tag %08x at %zu\n", vec_path, tag, pos - 4);
            rc = 2; break;
        }
    }
    if (!ended || pos != buf.size()) rc = 2;
    if (fclose(out) != 0) rc = 2;
    printf("RESULT cycles=%llu busy_cycles=%llu batches=%u\n",
        (unsigned long long)(cycles - start_cycles),
        (unsigned long long)(busy_cycles - start_busy), batches);
    return rc;
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    tb = new Vtb_gpu;
    int worst = 0;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (argv[i][0] == '+') { i--; continue; }
        int rc;
        try { rc = run_vector(argv[i], argv[i + 1]); }
        catch (const std::exception &e) { fprintf(stderr, "%s\n", e.what()); rc = 2; }
        if (rc) fprintf(stderr, "vector %s rc=%d\n", argv[i], rc);
        if (rc > worst) worst = rc;
    }
    fprintf(stderr, "rtl cycles=%llu\n", (unsigned long long)cycles);
    tb->final();
    delete tb;
    return worst;
}
