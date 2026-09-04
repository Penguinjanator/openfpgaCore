//------------------------------------------------------------------------------
// tb_settle_probe_main — reads sdram_model_full's A/BA command-setup settle
// checker after driving representative word traffic through io_sdram.
// Additive, bench-only.  PASS criteria (Stage-A early address drive,
// BANK_ROW_TRACK=1, no burst-write beats driven):
//   chk_cmd_setup0 == 0  &&  chk_min_setup >= 1  &&  model errors == 0
//------------------------------------------------------------------------------
#include "Vtb_settle_probe.h"
#include "Vtb_settle_probe___024root.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <functional>

static Vtb_settle_probe *tb;
static vluint64_t sim_cycles = 0;

static void tick() {
    tb->clk = 0; tb->eval();
    tb->clk = 1; tb->eval();
    sim_cycles++;
}

static bool wait_for(std::function<bool()> cond, int timeout, const char *what) {
    for (int i = 0; i < timeout; i++) { tick(); if (cond()) return true; }
    printf("TIMEOUT waiting for %s (%d cycles)\n", what, timeout);
    printf("  post-timeout ctrl_state trace:");
    for (int i = 0; i < 24; i++) { tick(); printf(" %d", (int)tb->ctrl_state); }
    printf("\n");
    return false;
}

struct ChkSnap { int32_t total, setup0, min, last, errors; };
static ChkSnap snap() {
    auto *r = tb->rootp;
    return { (int32_t)r->tb_settle_probe__DOT__sdram_chip__DOT__chk_cmd_total,
             (int32_t)r->tb_settle_probe__DOT__sdram_chip__DOT__chk_cmd_setup0,
             (int32_t)r->tb_settle_probe__DOT__sdram_chip__DOT__chk_min_setup,
             (int32_t)r->tb_settle_probe__DOT__sdram_chip__DOT__chk_last_setup,
             (int32_t)r->tb_settle_probe__DOT__sdram_chip__DOT__errors };
}

static int failures = 0;

static void word_write(uint32_t addr, uint32_t data) {
    tb->word_wr = 1; tb->word_rd = 0;
    tb->word_addr = addr & 0xffffff; tb->word_data = data;
    tb->word_wstrb = 0xf; tb->word_burst_len = 0;
    tick();
    tb->word_wr = 0;
    if (!wait_for([]{ return tb->word_wr_done; }, 2000, "word_wr_done")) failures++;
}

static uint32_t word_read(uint32_t addr, int burst_words = 1) {
    tb->word_rd = 1; tb->word_wr = 0;
    tb->word_addr = addr & 0xffffff;
    tb->word_burst_len = (burst_words - 1) & 0xf;
    tick();
    tb->word_rd = 0;
    uint32_t last = 0;
    for (int w = 0; w < burst_words; w++) {
        if (!wait_for([]{ return tb->word_q_valid; }, 2000, "word_q_valid")) { failures++; break; }
        last = tb->word_q;
    }
    tb->word_burst_len = 0;
    return last;
}

static void print_snap(const char *tag, ChkSnap s, ChkSnap base) {
    int32_t total = s.total - base.total, s0 = s.setup0 - base.setup0;
    printf("  [%s] addr-consuming cmds=%d  settle==0 edges=%d  min_settle(global)=%d  last=%d  model_errors=%d\n",
           tag, total, s0, s.min, s.last, s.errors);
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    tb = new Vtb_settle_probe;

    // Reset
    tb->clk = 0; tb->reset_n = 0;
    tb->word_rd = tb->word_wr = 0; tb->word_addr = 0; tb->word_data = 0;
    tb->word_wstrb = 0; tb->word_burst_len = 0;
    tb->burst_rd = 0; tb->burst_addr = 0; tb->burst_len = 0;
    for (int i = 0; i < 10; i++) tick();
    tb->reset_n = 1;

    // Boot/init: 30000-cycle CKE delay + PRECHG-ALL/AUTOREF/LMR, then IDLE(7)
    if (!wait_for([]{ return tb->ctrl_state == 7; }, 40000, "ST_IDLE after init"))
        return 2;
    ChkSnap after_init = snap();
    print_snap("init (PRECHG-ALL + LMR)", after_init, {0,0,0,0,0});

    // ---- Phase 1: 8 single writes scattered across banks/rows (ACT+WRITE+PRECHG)
    for (int i = 0; i < 8; i++)
        word_write(0x000000 + i * 0x41000, 0xA0B00000u + i);   // bank/row scatter
    ChkSnap p1 = snap(); print_snap("P1 8 scattered single writes", p1, after_init);

    // ---- Phase 2: read them back (ACT+READ), verify data
    for (int i = 0; i < 8; i++) {
        uint32_t v = word_read(0x000000 + i * 0x41000);
        if (v != 0xA0B00000u + i) {
            printf("  DATA MISMATCH @%06x: got %08x want %08x\n", i * 0x41000, v, 0xA0B00000u + i);
            failures++;
        }
    }
    ChkSnap p2 = snap(); print_snap("P2 8 scattered single reads", p2, p1);

    // ---- Phase 3: row-hit ping-pong across two banks (READ w/o ACT path)
    for (int i = 0; i < 16; i++)
        word_read((i & 1) ? 0x041000 : 0x000000);
    ChkSnap p3 = snap(); print_snap("P3 16 alternating-bank row-hit reads", p3, p2);

    // ---- Phase 4: 16-word cache-line fill (word burst read)
    for (int i = 0; i < 16; i++) word_write(0x002000 + i, 0x51000000u + i);
    word_read(0x002000, 16);
    ChkSnap p4 = snap(); print_snap("P4 16-word line writes + 16-beat burst read", p4, p3);

    // ---- Phase 5: scanout-style burst_rd, 64 words
    // ONE-cycle pulse, as production scanout drives it: a multi-cycle pulse
    // re-arms burst_rd_queue and the ghost dispatch samples burst_len LIVE
    // (see the P5 ghost-burst note in the settle report).
    tb->burst_addr = 0x004000; tb->burst_len = 64; tb->burst_rd = 1;
    tick();
    tb->burst_rd = 0;
    if (!wait_for([]{ return tb->burst_data_done; }, 5000, "burst_data_done")) failures++;
    tb->burst_len = 0;
    ChkSnap p5 = snap(); print_snap("P5 64-word scanout burst read", p5, p4);

    // ---- Phase 6: idle long enough to catch auto-refresh + next-op PRECHG interplay
    for (int i = 0; i < 4000; i++) tick();
#ifdef SETTLE_TRACE
    {
        auto *r = tb->rootp;
        tb->word_rd = 1; tb->word_wr = 0; tb->word_addr = 0; tb->word_burst_len = 0;
        tick();
        tb->word_rd = 0;
        for (int i = 0; i < 60; i++) {
            printf("  t+%02d st=%2d cmd=%d ncs=%d t2=%d len=%d dc=%d rp=%d rq=%d\n", i,
                (int)tb->ctrl_state,
                (int)r->tb_settle_probe__DOT__sdram_ctrl__DOT__cmd,
                (int)tb->rootp->tb_settle_probe__DOT__sdram_ctrl__DOT__phy_ncs,
                (int)r->tb_settle_probe__DOT__sdram_ctrl__DOT__t2_done,
                (int)r->tb_settle_probe__DOT__sdram_ctrl__DOT__length,
                (int)r->tb_settle_probe__DOT__sdram_ctrl__DOT__dc,
                (int)r->tb_settle_probe__DOT__sdram_ctrl__DOT__refresh_pending,
                (int)r->tb_settle_probe__DOT__sdram_ctrl__DOT__word_rd_queue);
            tick();
        }
        return 3;
    }
#endif
    word_read(0x000000);
    ChkSnap p6 = snap(); print_snap("P6 refresh window + post-refresh read", p6, p5);

    ChkSnap fin = snap();
    printf("\n==== settle summary (whole run) ====\n");
    printf("address-consuming command edges : %d\n", fin.total);
    printf("edges with settle == 0 (1T-late): %d\n", fin.setup0);
    printf("minimum settle at any edge      : %d cycle(s)\n", fin.min);
    printf("model protocol errors           : %d\n", fin.errors);
    printf("simulated cycles                : %llu\n", (unsigned long long)sim_cycles);

    bool pass = (failures == 0) && (fin.errors == 0) && (fin.total > 0)
             && (fin.setup0 == 0) && (fin.min >= 1);
    printf("=== Results: %s — %s ===\n", pass ? "PASS" : "FAIL",
           pass ? "every command decoded with A/BA stable >= 1 full cycle"
                : "settle==0 edges present, data/timeout failure, or model errors");
    delete tb;
    return pass ? 0 : 1;
}
