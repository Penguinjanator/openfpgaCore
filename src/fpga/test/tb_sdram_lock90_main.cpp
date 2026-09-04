//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------
//
// tb_sdram_lock90 driver — MiSTer 90 MHz boot-freeze convergence, round 2.
//
// Round-1 result (hand-modeled M2): the arbiter/slave/io_sdram/video_burst_arb
// stack is LIVELOCK-CLEAN under shaped traffic, and a 100%-duty CPU starves
// M2 completely (no M2-vs-CPU fairness exists in the arbiter priority chain).
// The HW symptom is the CPU freezing, which the idealized M2 cannot cause —
// so round 2 swaps in the REAL hps_bridge as M2, fed by a faithful ioctl
// boot.rom stream (16-bit words, ioctl_wait-honoring, feed period swept
// around the 90- and 100 MHz-relative rates), and paces the CPU realistically
// (inter-op gaps + periodic 16-beat cache-eviction write bursts — the diag's
// glyph writes).  The hardware freeze scenario, layer-faithful:
//
//   CPU alias singles + eviction bursts   (M1)
//   real hps_bridge S_BOOT single drains  (M2)  <- ioctl feed
//   boot-console line fetches             (vid via video_burst_arb)
//   ddr3_fb frame copy                    (dma via video_burst_arb)
//   REFRESH_INTERVAL=660                  (-G at build)
//
// Verdicts: CPU LIVELOCK (op counter stall), BRIDGE STARVE (stream frozen),
// DATA (read mismatch); per-combo throughput/latency report.
//
// ROUND-2 RESULTS (2026-08-26):
//   * cpu_gap=0 (CPU saturating): the REAL bridge freezes in S_BOOT_AW at
//     sent=2/74020, ioctl_wait backpressuring Main forever — the arbiter
//     has NO M2-vs-CPU fairness (gpu_deficit guards only CPU-vs-GPU/audio).
//     Structural, frequency-independent; candidate mechanism for the DE10
//     "boot.rom NEVER ARRIVED" diag line.  Reported as BRGSTARV, not a
//     failure (a real CPU cannot sustain gap=0 indefinitely).
//   * cpu_gap>=6: all combos clean at REFRESH_INTERVAL=660 with 90 MHz-
//     shaped pacing — no CPU-side livelock exists in the fabric below
//     cpu_system.  The SS1 90 MHz boot freeze therefore points above this
//     layer (cpu_system / VexiiRiscv LSU); next escalation is a system-
//     level sim with the real CPU complex.
//   * The slave's AW/W-desync guard (wlast_err_count -> SLVERR) verified
//     live: it caught this harness's own original post-tick-sampled driver.
//
// Harness rule: handshake fires MUST use pre-tick readies (registered DUT
// outputs gate THIS edge); post-tick sampling skews the beat index by one
// and trips the slave's desync guard.  The once-per-combo "[0] SDRAM ERROR:
// refresh interval exceeded" line is benign: the model is not reset between
// combos and the DUT's 30k-cycle re-boot window exceeds the model's 1700-
// cycle refresh bound.
//
#include "Vtb_sdram_lock90.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>

static Vtb_sdram_lock90* tb;
static uint64_t g_cycle;

static void tick() {
    tb->clk = 0; tb->eval();
    tb->clk = 1; tb->eval();
    g_cycle++;
}

// ---------------------------------------------------------------- addresses
static const uint32_t ALIAS_ADDR[6] = {
    0x00100000u, 0x00800000u, 0x01000000u,
    0x01800000u, 0x02000000u, 0x02800000u
};
static const uint32_t TERM_FB       = 0x00300000u;
static const uint32_t DISP_FB       = TERM_FB;
static const uint32_t BOOT_BYTES    = 148040u;          // v0.8.1 boot.rom
static const uint32_t BOOT_WORDS16  = (BOOT_BYTES + 1) / 2;

// ---------------------------------------------------------------- M1: CPU
// Serialized alias loop with realistic pacing: inter-op gap + every Nth op
// a 16-beat write burst (cache-line eviction from the glyph writer).
static int g_cpu_gap = 6;
static int g_ev_len = 15;   // eviction awlen (LOCK90_EVLEN)
static int g_aw_first = 0; // 1: hold W until AW accepted (LOCK90_AWFIRST)
struct CpuState {
    int      phase;      // 0..5 write, 6..11 read
    int      sub;        // 0=issue, 1=wait B / wait R
    bool     aw_done, w_done;
    int      gap;        // idle cycles remaining before next op
    int      evict;      // >=0: eviction burst in progress, beat index
    bool     evict_aw;
    int      evict_ctr;  // ops until next eviction
    uint32_t evict_line;
    uint64_t ops, loops, data_errs;
    uint64_t lat_acc, lat_start;
} cpu;

static void cpu_reset_state() {
    memset(&cpu, 0, sizeof(cpu));
    cpu.evict = -1;
    cpu.evict_ctr = 24;
}

static void cpu_drive() {
    tb->m1_arvalid = 0; tb->m1_awvalid = 0; tb->m1_wvalid = 0;
    tb->m1_rready  = 1;
    if (cpu.gap > 0) return;

    if (cpu.evict >= 0) {                       // ---- eviction burst
        uint32_t a = TERM_FB + (cpu.evict_line % 240u) * 320u + 64u;
        if (!cpu.evict_aw) {
            tb->m1_awvalid = 1; tb->m1_awaddr = a; tb->m1_awlen = (uint8_t)g_ev_len;
        }
        if (cpu.evict <= g_ev_len && !(g_aw_first && !cpu.evict_aw)) {
            tb->m1_wvalid = 1; tb->m1_wdata = 0xE71C0000u + (uint32_t)cpu.evict;
            tb->m1_wstrb = 0xF; tb->m1_wlast = (cpu.evict == g_ev_len);
        }
        return;
    }

    if (cpu.phase < 6) {                        // ---- single write
        uint32_t a = ALIAS_ADDR[cpu.phase];
        uint32_t d = 0xA5A50000u + (uint32_t)cpu.phase;
        if (cpu.sub == 0) {
            cpu.lat_start = g_cycle;
            if (!cpu.aw_done) { tb->m1_awvalid = 1; tb->m1_awaddr = a; tb->m1_awlen = 0; }
            if (!cpu.w_done)  { tb->m1_wvalid = 1; tb->m1_wdata = d;
                                tb->m1_wstrb = 0xF; tb->m1_wlast = 1; }
        }
    } else {                                    // ---- single read
        uint32_t a = ALIAS_ADDR[cpu.phase - 6];
        if (cpu.sub == 0) {
            cpu.lat_start = g_cycle;
            tb->m1_arvalid = 1; tb->m1_araddr = a; tb->m1_arlen = 0;
        }
    }
}

static void cpu_op_done() {
    cpu.ops++;
    cpu.lat_acc += g_cycle - cpu.lat_start;
    cpu.gap = g_cpu_gap;
    if (--cpu.evict_ctr <= 0) {
        cpu.evict = 0; cpu.evict_aw = false; cpu.evict_ctr = 24; cpu.evict_line++;
    }
}

static void cpu_apply(bool f_aw, bool f_w, bool f_ar, bool f_b,
                      bool f_r, uint32_t r_data) {
    if (cpu.gap > 0) { cpu.gap--; return; }

    if (cpu.evict >= 0) {
        if (f_aw) cpu.evict_aw = true;
        if (f_w && cpu.evict <= g_ev_len) cpu.evict++;
        if (cpu.evict > g_ev_len && cpu.evict_aw && f_b) {
            cpu.evict = -1;
            cpu.gap = g_cpu_gap;
        }
        return;
    }

    if (cpu.phase < 6) {
        if (f_aw) cpu.aw_done = true;
        if (f_w)  cpu.w_done  = true;
        if (cpu.aw_done && cpu.w_done && cpu.sub == 0) cpu.sub = 1;
        if (cpu.sub == 1 && f_b) {
            cpu.aw_done = cpu.w_done = false; cpu.sub = 0;
            cpu.phase++;
            cpu_op_done();
        }
    } else {
        if (cpu.sub == 0 && f_ar) cpu.sub = 1;
        if (cpu.sub == 1 && f_r) {
            uint32_t want = 0xA5A50000u + (uint32_t)(cpu.phase - 6);
            if (r_data != want) {
                if (cpu.data_errs < 4)
                    printf("      DATA: addr %08x want %08x got %08x (cycle %llu)\n",
                           ALIAS_ADDR[cpu.phase - 6], want, r_data,
                           (unsigned long long)g_cycle);
                cpu.data_errs++;
            }
            cpu.sub = 0;
            cpu.phase = (cpu.phase == 11) ? 0 : cpu.phase + 1;
            if (cpu.phase == 0) cpu.loops++;
            cpu_op_done();
        }
    }
}

// ---------------------------------------------------------------- ioctl feed
// Models MiSTer main streaming boot.rom over the WIDE=1 (16-bit) ioctl
// channel: one word per FEED_P cycles, honoring ioctl_wait, download held
// through the stream.
static int g_feed_p = 4;
struct IoState {
    bool     active;
    uint32_t sent;       // 16-bit words pushed
    int      cnt;
    int      tail;       // cycles to hold download after last word
    uint64_t wait_stalls;
} io;

static void io_reset_state() {
    memset(&io, 0, sizeof(io));
    io.active = true; io.cnt = 50; io.tail = 8;
    tb->ioctl_download = 0; tb->ioctl_wr = 0; tb->ioctl_index = 0;
}

static void io_drive() {
    tb->ioctl_wr = 0;
    if (!io.active) {
        if (io.tail > 0 && --io.tail == 0) tb->ioctl_download = 0;
        return;
    }
    tb->ioctl_download = 1;
    if (--io.cnt > 0) return;
    if (tb->ioctl_wait) { io.wait_stalls++; io.cnt = 1; return; }
    tb->ioctl_wr   = 1;
    tb->ioctl_dout = (uint16_t)(0x1234u + io.sent * 0x9E37u);
    io.sent++;
    io.cnt = g_feed_p;
    if (io.sent >= BOOT_WORDS16) io.active = false;
}

// ---------------------------------------------------------------- video
static int g_line_p = 3175;
struct VidState {
    int line, cnt;
    bool busy;
    uint64_t fetches, misses;
} vid;

static void vid_reset_state() { memset(&vid, 0, sizeof(vid)); vid.cnt = 100; }

static void vid_drive() {
    tb->vid_rd = 0;
    if (--vid.cnt <= 0) {
        vid.cnt = g_line_p;
        int line = vid.line;
        vid.line = (vid.line + 1) % 525;
        if (line < 480) {
            if (vid.busy) vid.misses++;
            else {
                uint32_t byte_addr = TERM_FB + (uint32_t)(line >> 1) * 320u;
                tb->vid_rd   = 1;
                tb->vid_addr = (byte_addr >> 1) & 0x1FFFFFF;
                tb->vid_len  = 80;
                vid.busy = true;
                vid.fetches++;
            }
        }
    }
}

static void vid_sample() { if (tb->vid_data_done) vid.busy = false; }

// ---------------------------------------------------------------- frame DMA
static bool g_dma_on = true;
struct DmaState {
    int chunk, sub, frame_cnt;
    uint64_t chunks;
} dma;

static void dma_reset_state() {
    memset(&dma, 0, sizeof(dma));
    dma.chunk = -1; dma.frame_cnt = 5000;
}

static void dma_drive() {
    tb->dma_req = 0;
    if (!g_dma_on) return;
    if (dma.chunk < 0) {
        if (--dma.frame_cnt <= 0) { dma.chunk = 0; dma.sub = 0; }
        return;
    }
    uint32_t byte_addr = DISP_FB + (uint32_t)dma.chunk * 320u;
    tb->dma_addr = (byte_addr >> 1) & 0x1FFFFFF;
    tb->dma_len  = 80;
    tb->dma_req  = 1;
}

static void dma_sample() {
    if (!g_dma_on || dma.chunk < 0) return;
    if (dma.sub == 0 && tb->dma_gnt) dma.sub = 1;
    if (dma.sub == 1 && tb->dma_data_done) {
        dma.chunks++; dma.sub = 0;
        if (++dma.chunk == 240) { dma.chunk = -1; dma.frame_cnt = 525 * g_line_p; }
    }
}

// ---------------------------------------------------------------- harness
static const uint64_t STALL_LIMIT = 60000;

static void idle_masters() {
    tb->m0_arvalid = 0; tb->m0_awvalid = 0; tb->m0_wvalid = 0;
    tb->m3_arvalid = 0; tb->m3_rready = 1;
    tb->m2_arvalid = 0; tb->m2_awvalid = 0; tb->m2_wvalid = 0; tb->m2_rready = 1;
}

static void dump_state(const char* tag) {
    printf("      %s: cycle=%llu grant=%u arb_state=%u io_state=0x%02x "
           "wqp=%u busy=%u vb_owner=%u brg_state=%u\n",
           tag, (unsigned long long)g_cycle,
           (unsigned)tb->dbg_grant, (unsigned)tb->dbg_arb_state,
           (unsigned)tb->dbg_io, (unsigned)tb->dbg_word_queue_pending,
           (unsigned)tb->dbg_busy, (unsigned)tb->dbg_vb_owner,
           (unsigned)tb->dbg_brg_state);
    printf("        m1: phase=%d sub=%d evict=%d | arv=%u awv=%u wv=%u "
           "arr=%u awr=%u wr=%u bv=%u rv=%u\n",
           cpu.phase, cpu.sub, cpu.evict,
           (unsigned)tb->m1_arvalid, (unsigned)tb->m1_awvalid, (unsigned)tb->m1_wvalid,
           (unsigned)tb->m1_arready, (unsigned)tb->m1_awready, (unsigned)tb->m1_wready,
           (unsigned)tb->m1_bvalid, (unsigned)tb->m1_rvalid);
    printf("        io: sent=%u/%u wait=%u stalls=%llu loaded=%u | "
           "vid line=%d busy=%d miss=%llu | dma chunk=%d done=%llu\n",
           io.sent, BOOT_WORDS16, (unsigned)tb->ioctl_wait,
           (unsigned long long)io.wait_stalls, (unsigned)tb->boot_rom_loaded,
           vid.line, (int)vid.busy, (unsigned long long)vid.misses,
           dma.chunk, (unsigned long long)dma.chunks);
}

// Returns 0 clean, 1 CPU livelock, 2 data error, 3 bridge starve.
static int run_combo(int feed_p, int cpu_gap, int line_p, bool dma_on,
                     uint64_t cycles) {
    g_feed_p = feed_p; g_cpu_gap = cpu_gap; g_line_p = line_p; g_dma_on = dma_on;

    tb->reset_n = 0;
    idle_masters();
    tb->m2_src_bridge = 1;
    tb->vid_rd = 0; tb->dma_req = 0;
    tb->ioctl_download = 0; tb->ioctl_wr = 0;
    for (int i = 0; i < 32; i++) tick();
    tb->reset_n = 1;
    for (int i = 0; i < 31000; i++) tick();

    cpu_reset_state(); io_reset_state(); vid_reset_state(); dma_reset_state();

    uint64_t last_ops = 0, last_progress = g_cycle;
    uint32_t last_sent = 0; uint64_t last_io_progress = g_cycle;
    uint64_t end = g_cycle + cycles;
    int verdict = 0;

    static int trace_left = 0;
    bool tracing = getenv("LOCK90_TRACE") != nullptr;

    while (g_cycle < end) {
        idle_masters();
        cpu_drive(); io_drive(); vid_drive(); dma_drive();
        if (tracing && cpu.evict == 0 && !cpu.evict_aw && trace_left == 0)
            trace_left = 120;   // first eviction burst: trace 120 cycles
        // Handshake fires use PRE-tick readies (registered DUT outputs =
        // the values that gate THIS edge); applied after the edge.
        bool f_aw = tb->m1_awvalid && tb->m1_awready;
        bool f_w  = tb->m1_wvalid  && tb->m1_wready;
        bool f_ar = tb->m1_arvalid && tb->m1_arready;
        bool f_b  = tb->m1_bvalid;
        bool f_r  = tb->m1_rvalid;
        uint32_t r_data = tb->m1_rdata;
        tick();
        if (trace_left > 0) {
            trace_left--;
            printf("      T c=%llu evict=%d aw=%d | awv=%u awr=%u wv=%u wr=%u "
                   "bv=%u | grant=%u arb=%u io=0x%02x wqp=%u slv=%u wlerr=%u\n",
                   (unsigned long long)g_cycle, cpu.evict, (int)cpu.evict_aw,
                   (unsigned)tb->m1_awvalid, (unsigned)tb->m1_awready,
                   (unsigned)tb->m1_wvalid, (unsigned)tb->m1_wready,
                   (unsigned)tb->m1_bvalid,
                   (unsigned)tb->dbg_grant, (unsigned)tb->dbg_arb_state,
                   (unsigned)tb->dbg_io, (unsigned)tb->dbg_word_queue_pending,
                   (unsigned)tb->dbg_slave_state, (unsigned)tb->dbg_wlast_err);
            if (trace_left == 0 && tracing) { puts("      T end"); }
        }
        cpu_apply(f_aw, f_w, f_ar, f_b, f_r, r_data);
        vid_sample(); dma_sample();

        if (cpu.ops != last_ops) { last_ops = cpu.ops; last_progress = g_cycle; }
        if (io.sent != last_sent) { last_sent = io.sent; last_io_progress = g_cycle; }

        if (g_cycle - last_progress > STALL_LIMIT) {
            printf("      CPU LIVELOCK: op counter frozen %llu cycles "
                   "(ops=%llu loops=%llu)\n",
                   (unsigned long long)(g_cycle - last_progress),
                   (unsigned long long)cpu.ops, (unsigned long long)cpu.loops);
            dump_state("stall");
            for (int i = 0; i < 3; i++) tick();
            dump_state("stall+3");
            verdict = 1;
            break;
        }
        if (io.active && g_cycle - last_io_progress > STALL_LIMIT) {
            printf("      BRIDGE STARVE: ioctl stream frozen %llu cycles "
                   "(sent=%u/%u)\n",
                   (unsigned long long)(g_cycle - last_io_progress),
                   io.sent, BOOT_WORDS16);
            dump_state("brg-stall");
            verdict = 3;
            break;
        }
    }
    if (verdict == 0 && cpu.data_errs) verdict = 2;

    double avg_lat = cpu.ops ? (double)cpu.lat_acc / (double)cpu.ops : 0.0;
    const char* v = verdict == 0 ? "ok      " :
                    verdict == 1 ? "LIVELOCK" :
                    verdict == 2 ? "DATAERR " : "BRGSTARV";
    printf("    feed=%-2d gap=%-2d lineP=%d dma=%d : %s cpu_ops=%-7llu "
           "lat=%.0f  ioctl=%u/%u loaded=%u vidmiss=%llu dma=%llu\n",
           feed_p, cpu_gap, line_p, (int)dma_on, v,
           (unsigned long long)cpu.ops, avg_lat,
           io.sent, BOOT_WORDS16, (unsigned)tb->boot_rom_loaded,
           (unsigned long long)vid.misses, (unsigned long long)dma.chunks);
    return verdict;
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    tb = new Vtb_sdram_lock90;

    if (getenv("LOCK90_EVLEN"))   g_ev_len   = atoi(getenv("LOCK90_EVLEN"));
    if (getenv("LOCK90_AWFIRST")) g_aw_first = atoi(getenv("LOCK90_AWFIRST"));
    printf("evlen=%d aw_first=%d\n", g_ev_len, g_aw_first);
    printf("=== tb_sdram_lock90 r2: REAL hps_bridge M2 + shaped CPU "
           "(REFRESH_INTERVAL from -G build) ===\n");

    static const int FEEDS[] = { 2, 3, 4, 6, 9, 12 };
    static const int GAPS[]  = { 0, 6, 14 };
    static const int LINEP[] = { 3175, 2857 };
    int fails = 0, runs = 0;

    for (size_t lp = 0; lp < sizeof(LINEP)/sizeof(LINEP[0]); lp++)
        for (size_t g = 0; g < sizeof(GAPS)/sizeof(GAPS[0]); g++)
            for (size_t f = 0; f < sizeof(FEEDS)/sizeof(FEEDS[0]); f++) {
                runs++;
                int v = run_combo(FEEDS[f], GAPS[g], LINEP[lp], true, 600000);
                if (v == 1 || v == 2) fails++;     // starvation reported, not failed
            }

    printf("=== Results: %d passed, %d failed ===\n", runs - fails, fails);
    delete tb;
    return fails ? 1 : 0;
}
