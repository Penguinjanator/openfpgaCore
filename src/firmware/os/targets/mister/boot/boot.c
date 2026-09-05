//------------------------------------------------------------------------------
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileType: SOURCE
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
//------------------------------------------------------------------------------

/*
 * openfpgaOS Bootloader — MiSTer
 *
 * Runs from BRAM.  The MiSTer framework auto-delivers boot.rom (= os.bin)
 * over ioctl at core start; hps_bridge.v DMAs the byte stream into the
 * SDRAM staging arena and raises HPS_STATUS_BOOT_LOADED.  This loader
 * waits on that flag, copies the image from staging to its runtime VMA,
 * verifies the CRC trailer (append_os_crc.py), zeroes BSS/stack, and
 * jumps to os_main.
 *
 * Differences from the Pocket loader:
 *   - no APF ALLCOMPLETE wait, no CRAM0 mux, no datatable size query
 *     (HPS_BOOT_LEN carries the image size)
 *   - no PHDP/UART host discovery (the HPS is the delivery channel)
 *   - CRC-mismatch retries re-copy from staging (the staging copy itself
 *     is stable SDRAM, so retries only guard the SDRAM→SDRAM copy)
 *
 * IMPORTANT: This code runs BEFORE os.bin is loaded into SDRAM.
 * It must NOT call any HAL functions (they live in SDRAM).
 * All hardware access is done via direct register writes.
 */

#define BUILDING_BOOTLOADER
#include "../hal/regs.h"
#include "../targets/mister/hps_regs.h"

#define SHARED_ATTR __attribute__((section(".text.boot")))
#include "dcache_evict.inc.c"
#undef SHARED_ATTR

/* Trap context breadcrumbs (read by misaligned handler), kept in BRAM. */
volatile unsigned int __attribute__((section(".bss.boot"))) pd_dbg_stage;
volatile unsigned int __attribute__((section(".bss.boot"))) pd_dbg_info;

/* Counts staging→SDRAM copies that failed the CRC and were retried. */
volatile unsigned int __attribute__((section(".bss.boot"))) os_load_crc_retries;

/* OS image integrity trailer (append_os_crc.py): [magic 'OFC1'][crc32 LE]. */
#define OS_CRC_MAGIC         0x3143464Fu
#define OS_CRC_TRAILER_BYTES 8u
#define OS_LOAD_MAX_ATTEMPTS 4

/* Image-carried metadata block (append_os_crc.py), 16 bytes immediately
 * before the CRC trailer: [magic 'OSE2'][entry][bss_start][bss_end], LE,
 * covered by the CRC.
 *
 * WHY: this bootloader is baked into the bitstream while boot.rom
 * (os.bin) swaps freely.  Zeroing .bss and jumping to os_main via OUR
 * linked symbols uses bounds/entry frozen at bitstream build time — any
 * kernel whose layout shifted gets a stale .bss clear (tail statics
 * keep power-on DRAM junk → per-layout trap/hang: the 2026-07-02
 * MiSTer boot lottery) and/or a stale entry jump.  Prefer the loaded
 * image's own values; unstamped images fall back to the baked symbols. */
#define OS_META_MAGIC  0x3245534Fu
#define OS_META_BYTES  16u

/* Boot-ABI block (append_os_crc.py), 8 bytes immediately before the OSE2
 * block: [magic 'OABI'][boot_abi], LE, covered by the CRC.
 *
 * WHY: OSE2 fixed the entry/.bss drift, but the bootloader still bakes in
 * memory-map constants (staging offset, the CRC base _osdata_init_vma_start,
 * the SDRAM window) that OSE2 does NOT carry.  A wrong-target or stale
 * mif+os.bin pair still passes the CRC (which is content-, not layout-checked)
 * and then loads/runs the image at the wrong addresses → silent black.  The
 * Makefile -D's OF_TARGET_BOOT_ABI (a hash of the target + those constants)
 * into this bootloader AND stamps the same value into os.bin; we compare them
 * below and stop with a visible message on mismatch.  Unstamped images (no
 * OABI block, or a build that injected no id) skip the check. */
#ifndef OF_TARGET_BOOT_ABI
#define OF_TARGET_BOOT_ABI 0u   /* build injected no id → check disabled */
#endif
#define OS_ABI_MAGIC   0x4942414Fu   /* 'OABI' read LE from SDRAM */
#define OS_ABI_BYTES   8u

#define BOOT_ROM_WAIT_CYCLES 1000000000u   /* ~10 s for HPS file delivery */
#define BOOT_OS_SIZE_MAX     (768u * 1024u)
#define BOOT_CACHE_LINE_SIZE 64u
#define BOOT_HW_IDLE_TIMEOUT 1000000u

#define BOOT_GPU_REG(offset)     REG32(OF_TARGET_GPU_BASE + (offset))
#define BOOT_GPU_CTRL            BOOT_GPU_REG(0x00u)
#define BOOT_GPU_STATUS          BOOT_GPU_REG(0x14u)
#define BOOT_GPU_DMA_SRC         BOOT_GPU_REG(0x0Cu)
#define BOOT_GPU_DMA_LEN         BOOT_GPU_REG(0x1Cu)
#define BOOT_GPU_TEX_FLUSH       BOOT_GPU_REG(0x28u)
#define BOOT_GPU_CTRL_SOFT_RESET (1u << 1)
#define BOOT_GPU_CTRL_RING_RESET (1u << 2)
#define BOOT_GPU_STATUS_DMA_BUSY (1u << 2)

#define BOOT_LINK_CTRL_RESET     (1u << 1)

/* os.bin staging copy in the arena, via the uncached alias. */
#define BOOT_STAGE_UNCACHED  (SDRAM_UNCACHED_BASE + OF_TARGET_CRAM0_BRIDGE + \
                              OF_TARGET_CRAM0_OS_OFFSET)

/* External symbols from linker */
extern char _os_bss_start[], _os_bss_end[];
extern char _runtime_stack_top[];
extern char _os_copy_size[];
extern char _osdata_init_vma_start[];

/* OS entry point */
extern void os_main(void);
extern void switch_to_runtime_stack_and_call(void (*entry)(void), void *stack_top);

__attribute__((section(".text.boot")))
static uintptr_t boot_sdram_uncached_addr(const void *addr) {
    uint32_t a = (uint32_t)(uintptr_t)addr;
    if (a >= SDRAM_BASE && a < SDRAM_BASE + SDRAM_SIZE)
        return (uintptr_t)(a - SDRAM_BASE + SDRAM_UNCACHED_BASE);
    return (uintptr_t)a;
}

__attribute__((section(".text.boot")))
static void boot_dcache_inval_range(void *addr, uint32_t size) {
    if (size == 0)
        return;

    uintptr_t a = (uintptr_t)addr & ~(uintptr_t)(BOOT_CACHE_LINE_SIZE - 1u);
    uintptr_t end = (uintptr_t)addr + size;
    __asm__ volatile("fence" ::: "memory");
    for (; a < end; a += BOOT_CACHE_LINE_SIZE)
        __asm__ volatile(".insn i 0x0F, 2, x0, %0, 0" :: "r"(a) : "memory");
    __asm__ volatile("fence" ::: "memory");
}

__attribute__((section(".text.boot")))
static void boot_zero_uncached_sdram(uint32_t start, uint32_t end) {
    if (end <= start)
        return;

    volatile uint32_t *p =
        (volatile uint32_t *)boot_sdram_uncached_addr((void *)(uintptr_t)start);
    volatile uint32_t *e =
        (volatile uint32_t *)boot_sdram_uncached_addr((void *)(uintptr_t)end);
    while (p < e)
        *p++ = 0;
    __asm__ volatile("fence" ::: "memory");
}

/* Font in BRAM (.fastrodata) — defined in terminal.c */
extern const uint8_t font8x8[2048];

__attribute__((section(".text.boot")))
static void boot_palette_init(void) {
    PAL_INDEX = 15;
    PAL_WRITE = 0xFFFFFF;
    PAL_INDEX = PAL_INDEX_COMMIT;
}

__attribute__((section(".text.boot")))
static void boot_fb_putchar(int col, int row, char c) {
    if ((unsigned)col >= TERM_COLS || (unsigned)row >= TERM_ROWS) return;
    volatile uint8_t *fb = (volatile uint8_t *)TERM_FB_BASE;
    const uint8_t *glyph = &font8x8[(unsigned)(uint8_t)c * 8];
    int px = col * 8;
    int py = row * 8;
    for (int y = 0; y < 8; y++) {
        uint8_t bits = glyph[y];
        volatile uint8_t *dst = &fb[(py + y) * 320 + px];
        for (int x = 0; x < 8; x++) {
            dst[x] = (bits & 0x80) ? 15 : 0;  /* white on black */
            bits <<= 1;
        }
    }
}

__attribute__((section(".text.boot")))
static void boot_fb_puts(int col, int row, const char *s) {
    while (*s && col < TERM_COLS) {
        boot_fb_putchar(col, row, *s);
        col++;
        s++;
    }
}

__attribute__((section(".text.boot")))
static void boot_fb_clear_row(int row) {
    if ((unsigned)row >= TERM_ROWS) return;
    volatile uint8_t *fb = (volatile uint8_t *)TERM_FB_BASE;
    for (int i = 0; i < 320 * 8; i++)
        fb[row * 8 * 320 + i] = 0;
}


/* ===================================================================== *
 * OF_SDRAM_DIAG — board bring-up diagnostic (temporary; not shipped).
 *
 * A stock DE10-Nano with a pluggable dual-chip 128 MB module fails to
 * boot (staging->VMA copy fails CRC x3) while a SuperStation One with
 * soldered SDRAM is fine.  Two candidate faults look identical from a
 * distance: (a) byte masking dead -> sub-word writes land full width,
 * (b) read capture wrong -> everything read back is garbage.  This
 * prints enough to tell them apart from one photograph.
 *
 * The normal glyph writer stores ONE BYTE PER PIXEL, so it is unreadable
 * under fault (a) — that is exactly why the reporter's screen is
 * garbled.  Everything here renders with 32-bit stores instead.
 * ===================================================================== */
/* #define OF_SDRAM_DIAG 1 */ /* TEMP: 90 MHz + VCO-1080 SDRAM table (comment out
                          * for normal boot; `make firmware` = MIF patch,
                          * no refit, either way) */
#ifdef OF_SDRAM_DIAG

/* defined further down; the diagnostic needs it for the staging check */
__attribute__((section(".text.boot")))
static uint32_t boot_crc32_uncached(uint32_t cached_base, uint32_t len);

__attribute__((section(".text.boot")))
static void diag_putchar_w(int col, int row, char c) {
    if ((unsigned)col >= TERM_COLS || (unsigned)row >= TERM_ROWS) return;
    volatile uint32_t *fb = (volatile uint32_t *)TERM_FB_BASE;
    const uint8_t *glyph = &font8x8[(unsigned)(uint8_t)c * 8];
    int px = col * 8, py = row * 8;
    for (int y = 0; y < 8; y++) {
        uint8_t bits = glyph[y];
        uint32_t w0 = 0, w1 = 0;
        for (int x = 0; x < 4; x++)
            w0 |= (uint32_t)((bits & (0x80u >> x)) ? 15u : 0u) << (8 * x);
        for (int x = 0; x < 4; x++)
            w1 |= (uint32_t)((bits & (0x08u >> x)) ? 15u : 0u) << (8 * x);
        uint32_t idx = ((uint32_t)(py + y) * 320u + (uint32_t)px) >> 2;
        fb[idx]     = w0;      /* 8 pixels = 2 aligned words, no byte stores */
        fb[idx + 1] = w1;
    }
}

__attribute__((section(".text.boot")))
static void diag_puts(int col, int row, const char *s) {
    while (*s && col < TERM_COLS) diag_putchar_w(col++, row, *s++);
}

__attribute__((section(".text.boot")))
static void diag_hex32(int col, int row, uint32_t v) {
    /* Arithmetic, NOT a lookup table: a static const char[] is not reliably
     * readable this early (it rendered blank on HW), and the hex readings are
     * the whole point of this screen. */
    for (int i = 0; i < 8; i++) {
        uint32_t nib = (v >> (28 - 4 * i)) & 0xFu;
        diag_putchar_w(col + i, row,
                       (char)(nib < 10u ? ('0' + nib) : ('a' + nib - 10u)));
    }
}

__attribute__((section(".text.boot")))
static void diag_dec(int col, int row, uint32_t v) {
    char b[10]; int n = 0;
    if (!v) { diag_putchar_w(col, row, '0'); return; }
    while (v && n < 10) { b[n++] = (char)('0' + (v % 10)); v /= 10; }
    for (int i = 0; i < n; i++) diag_putchar_w(col + i, row, b[n - 1 - i]);
}

__attribute__((section(".text.boot")))
static void boot_sdram_diag(void) {
    volatile uint32_t *fb = (volatile uint32_t *)TERM_FB_BASE;
    for (int i = 0; i < (320 * 240) / 4; i++) fb[i] = 0;

    diag_puts(0, 1, "openfpgaOS SDRAM diagnostic");

    /* ---- 1. byte-lane / DQM test ------------------------------------
     * 44332211 = byte masking works.  44444444 (or any repeated byte)
     * = DQM never reaches the chip, sub-word writes land full width. */
    volatile uint32_t *w = (volatile uint32_t *)
        boot_sdram_uncached_addr((void *)(uintptr_t)(SDRAM_BASE + 0x01000000u));
    volatile uint8_t *b = (volatile uint8_t *)w;
    *w = 0x00000000u;
    __asm__ volatile("fence" ::: "memory");
    b[0] = 0x11; b[1] = 0x22; b[2] = 0x33; b[3] = 0x44;
    __asm__ volatile("fence" ::: "memory");
    uint32_t lanes = *w;
    diag_puts(0, 3, "byte lanes  :");
    diag_hex32(14, 3, lanes);
    diag_puts(23, 3, lanes == 0x44332211u ? "OK" : "BAD");

    /* ---- 2. ALIASING: write ALL first, then read ALL back ------------
     * A dual-chip / mis-sized module can fold high addresses onto low
     * ones.  Writing then immediately reading each address would still
     * pass, so the writes must all land BEFORE any read. */
    /* NB: 0x00300000 is the terminal framebuffer and 0x03300000 is the
     * os.bin staging window — writing either destroys what we are trying
     * to display or the image we are about to check. */
    const uint32_t addrs[6] = { SDRAM_BASE + 0x00100000u, SDRAM_BASE + 0x00800000u,
                                SDRAM_BASE + 0x01000000u, SDRAM_BASE + 0x01800000u,
                                SDRAM_BASE + 0x02000000u, SDRAM_BASE + 0x02800000u };
    for (int i = 0; i < 6; i++)
        *(volatile uint32_t *)boot_sdram_uncached_addr(
            (void *)(uintptr_t)addrs[i]) = 0xA5A50000u + (uint32_t)i;
    __asm__ volatile("fence" ::: "memory");
    uint32_t alias_bad = 0, alias_first = 0;
    for (int i = 0; i < 6; i++) {
        uint32_t got = *(volatile uint32_t *)boot_sdram_uncached_addr(
            (void *)(uintptr_t)addrs[i]);
        if (got != 0xA5A50000u + (uint32_t)i) {
            if (!alias_bad) alias_first = got;
            alias_bad++;
        }
    }
    diag_puts(0, 4, "alias 6addr :");
    if (alias_bad) { diag_puts(14, 4, "BAD got="); diag_hex32(23, 4, alias_first); }
    else diag_puts(14, 4, "OK (no fold)");

    /* ---- 3. VOLUME: 64K words (256 KB), comparable to a real os.bin --- */
    volatile uint32_t *bp = (volatile uint32_t *)
        boot_sdram_uncached_addr((void *)(uintptr_t)(SDRAM_BASE + 0x01100000u));
    for (uint32_t i = 0; i < 65536u; i++) bp[i] = 0xC0DE0000u ^ (i * 2654435761u);
    __asm__ volatile("fence" ::: "memory");
    /* v2 recorder: read ONCE into a local — v1 re-read bp[i] when
     * recording, and the transient had passed (photos showed got==exp).
     * Also classify the error TYPE: XOR popcount 1-2 = DQ-capture bit
     * flips; a got that equals the expected pattern of a DIFFERENT index
     * = wrong-address capture (the 2T/addr-margin class). */
    uint32_t bad = 0, first_idx = 0, first_got = 0, first_exp = 0;
    uint32_t bits1 = 0, bitsN = 0, wrongaddr = 0;
    for (uint32_t i = 0; i < 65536u; i++) {
        uint32_t exp = 0xC0DE0000u ^ (i * 2654435761u);
        uint32_t got = bp[i];
        if (got != exp) {
            if (!bad) { first_idx = i; first_got = got; first_exp = exp; }
            bad++;
            uint32_t x = got ^ exp;
            /* popcount via Kernighan, bounded */
            uint32_t n = 0, v = x;
            while (v && n < 3) { v &= v - 1u; n++; }
            if (n <= 2) bits1++;
            else {
                bitsN++;
                /* wrong-address check: does got match the pattern for
                 * SOME index?  Invert: idx = (got^0xC0DE0000)*inverse.
                 * 2654435761 * 244002641 == 1 (mod 2^32). */
                uint32_t cand = (got ^ 0xC0DE0000u) * 244002641u;
                if (cand < 65536u &&
                    got == (0xC0DE0000u ^ (cand * 2654435761u)))
                    wrongaddr++;
            }
        }
    }
    diag_puts(0, 5, "64Kword bad :");
    diag_dec(14, 5, bad);
    if (bad) {
        diag_puts(0, 6, "  exp"); diag_hex32(6, 6, first_exp);
        diag_puts(15, 6, "got"); diag_hex32(19, 6, first_got);
        diag_puts(0, 10, "  xor"); diag_hex32(6, 10, first_exp ^ first_got);
        diag_puts(15, 10, "i"); diag_hex32(17, 10, first_idx);
        /* error-class counters: 1-2 bit flips / multi-bit / of those,
         * exact other-index pattern hits */
        diag_puts(0, 14, "  b12/1oN/wadr:");
        diag_dec(16, 14, bits1);
        diag_dec(22, 14, bitsN);
        diag_dec(28, 14, wrongaddr);
    }

    /* ---- 4. STABILITY: re-read the SAME word 3x --------------------
     * Differing values across reads = READ capture is unstable.  Same
     * wrong value every time = the WRITE (or addressing) is at fault.
     * That distinction picks the fix, so it must be measured. */
    volatile uint32_t *sp = &bp[12345];
    uint32_t r1 = *sp, r2 = *sp, r3 = *sp;
    diag_puts(0, 7, "reread x3   :");
    diag_hex32(14, 7, r1); diag_hex32(23, 7, r2);
    diag_puts(0, 8, "            :");
    diag_hex32(14, 8, r3);
    diag_puts(23, 8, (r1 == r2 && r2 == r3) ? "STABLE" : "UNSTABLE");

    /* ---- 5. cached (cache-line burst) read of the same region -------- */
    volatile uint32_t *cp = (volatile uint32_t *)(uintptr_t)(SDRAM_BASE + 0x01100000u);
    boot_dcache_inval_range((void *)cp, 65536u * 4u);
    uint32_t cbad = 0;
    for (uint32_t i = 0; i < 65536u; i++)
        if (cp[i] != (0xC0DE0000u ^ (i * 2654435761u))) cbad++;
    diag_puts(0, 9, "cached  bad :");
    diag_dec(14, 9, cbad);

    /* ---- 6. THE ACTUAL FAILING PATH: HPS -> staging -------------------
     * boot.rom is DMA'd into staging by the HPS, NOT by the CPU, so none
     * of the above exercises the path that really breaks.  Wait for the
     * image, then CRC it IN PLACE twice: two different CRCs means reads
     * are unstable; one stable CRC that still mismatches means the image
     * arrived corrupt (or was written wrong). */
    diag_puts(0, 11, "waiting for boot.rom...");
    unsigned int t0 = SYS_CYCLE_LO;
    while (!(HPS_STATUS & HPS_STATUS_BOOT_LOADED) &&
           (SYS_CYCLE_LO - t0) <= BOOT_ROM_WAIT_CYCLES) { }
    if (!(HPS_STATUS & HPS_STATUS_BOOT_LOADED)) {
        diag_puts(0, 11, "boot.rom NEVER ARRIVED  ");
    } else {
        uint32_t len = HPS_BOOT_LEN;
        uint32_t stage_cached = OF_TARGET_CRAM0_BASE + OF_TARGET_CRAM0_OS_OFFSET;
        if (len < 16u || len > (2u * 1024u * 1024u)) len = 148040u;
        uint32_t c1 = boot_crc32_uncached(stage_cached, len - 8u);
        uint32_t c2 = boot_crc32_uncached(stage_cached, len - 8u);
        volatile const uint32_t *tr = (volatile const uint32_t *)
            boot_sdram_uncached_addr((void *)(uintptr_t)(stage_cached + len - 8u));
        uint32_t want = tr[1];
        diag_puts(0, 11, "stage len   :"); diag_hex32(14, 11, len);
        diag_puts(0, 12, "stage crc   :"); diag_hex32(14, 12, c1);
        diag_hex32(23, 12, c2);
        diag_puts(0, 13, "want crc    :"); diag_hex32(14, 13, want);
        diag_puts(23, 13, (c1 != c2) ? "READ UNSTABLE"
                                     : (c1 == want ? "MATCH" : "IMAGE BAD"));
    }

    /* Table painted; staging untouched (CRC'd in place).  RETURN so the
     * normal boot continues with boot-console scanout still armed — that
     * makes every later boot message (CRC retries, ABI banner, kernel
     * shell) visible on screen/screenshot, which a normal black-boot
     * hides. */
    /* HALT here: a remote tester has to photograph this table, and letting
     * the boot continue repaints/scrolls it away.  (Flip to a return if you
     * want the diag as a pre-boot banner on a board you can watch live.) */
    diag_puts(0, 15, "photograph this screen");
    while (1) { }
}
#endif /* OF_SDRAM_DIAG */

/* ===================================================================== *
 * Self-tuning clock (INCLUDE_CLK_AUTOTUNE cores; HPS_CLK_CTRL reads 0 and
 * this whole path self-gates on every other core).
 *
 * A marginal pluggable SDRAM module (the DE10 dual-chip 128 MB class)
 * corrupts reads at 100 MHz but is clean at 90 (HW-proven, 2026-09-04).
 * This code runs FROM BRAM, so it stays trustworthy on exactly the boards
 * whose SDRAM is failing: probe SDRAM first thing; on failure write the
 * request magic — the fabric pauses the HPS bridge, warm-resets this
 * domain (including this CPU), rewrites the PLL to 90 MHz, and re-enters
 * this boot ROM, which re-probes and carries on.  One-shot per power-up.
 *
 * The probe is the diag's 64K-word recorder shape (the pattern that
 * discriminated the failing class on the DE10 photos): pseudorandom
 * sweep at +0x01100000 (off the terminal FB at +0x00300000 and the
 * staging window at +0x03300000), uncached write pass, TWO uncached read
 * passes plus one cached (burst) pass — ~0.2%/word transient flips give
 * ~hundreds of hits per pass, so detection is certain.
 * ===================================================================== */
__attribute__((section(".text.boot")))
static int boot_sdram_probe_ok(void) {
    volatile uint32_t *bp = (volatile uint32_t *)
        boot_sdram_uncached_addr((void *)(uintptr_t)(SDRAM_BASE + 0x01100000u));
    for (uint32_t i = 0; i < 65536u; i++)
        bp[i] = 0xC0DE0000u ^ (i * 2654435761u);
    __asm__ volatile("fence" ::: "memory");

    uint32_t bad = 0;
    for (int pass = 0; pass < 2; pass++)
        for (uint32_t i = 0; i < 65536u; i++)
            if (bp[i] != (0xC0DE0000u ^ (i * 2654435761u)))
                bad++;

    /* Cached pass: exercises the burst-read path. */
    volatile uint32_t *cp =
        (volatile uint32_t *)(uintptr_t)(SDRAM_BASE + 0x01100000u);
    boot_dcache_inval_range((void *)(uintptr_t)cp, 65536u * 4u);
    for (uint32_t i = 0; i < 65536u; i++)
        if (cp[i] != (0xC0DE0000u ^ (i * 2654435761u)))
            bad++;

    return bad == 0;
}

__attribute__((section(".text.boot")))
static void boot_clk_request_switch(void) {
    /* Nothing after this write is reached: the fabric warm-resets this
     * CPU and restarts the boot ROM at 90 MHz. */
    HPS_CLK_CTRL = HPS_CLK_REQ_MAGIC;
    while (1) { }
}

/* #define OF_CLK_AUTOTUNE_FORCE 1 */ /* TEMP: force the 90 MHz switch on a
                          * HEALTHY board (validates the fallback path on
                          * the SS1 without a marginal module).  Enable +
                          * `make firmware` = MIF patch, no refit.  Ships
                          * DISABLED. */

__attribute__((section(".text.boot")))
static void boot_clk_autotune(void) {
    uint32_t ctrl = HPS_CLK_CTRL;
    if (!(ctrl & HPS_CLK_PRESENT))
        return;                       /* core lacks the feature: 0 read */

#ifdef OF_CLK_AUTOTUNE_FORCE
    if (!(ctrl & HPS_CLK_ATTEMPTED))
        boot_clk_request_switch();    /* unconditional: exercise the path */
#endif

    if (boot_sdram_probe_ok()) {
        /* Healthy at the current clock.  If that clock is the fallback,
         * leave a visible note (kernel console repaints later). */
        if (ctrl & HPS_CLK_IS_90)
            boot_fb_puts(0, 2, "SDRAM: 90 MHz (auto)");
        else if (ctrl & HPS_CLK_SWITCH_FAILED)
            boot_fb_puts(0, 2, "clock switch failed");
        return;
    }

    if (!(ctrl & HPS_CLK_ATTEMPTED))
        boot_clk_request_switch();    /* marginal at 100: drop to 90 */

    /* Already at the fallback and STILL failing: this is a hardware
     * fault no clock can fix.  Say so and stop (the message may render
     * imperfectly on a byte-lane-broken board, but any text beats the
     * old silent black screen). */
    boot_fb_puts(0, 0, "SDRAM unstable even at 90 MHz");
    boot_fb_puts(0, 1, "hardware fault: check module seating");
    while (1) { }
}

/* os_finalize_memory() lives in BRAM .fasttext.  It only zeroes .bss. */
extern void os_finalize_memory(void *bss_start, void *bss_end);

__attribute__((section(".text.boot")))
static void flush_icache(void) {
    __asm__ volatile("fence");
    __asm__ volatile(".word 0x0000100f");  /* fence.i */
}

__attribute__((section(".text.boot")))
static void boot_hw_stabilize(void) {
    __asm__ volatile("fence" ::: "memory");

    /* Stale interrupt enables/pending bits are the most dangerous warm-boot
     * leftovers. */
    IRQ_MASK = 0;
    TIMER_CTRL = TIMER_CTRL_W1C_IRQ;
    VSYNC_IRQ_PENDING = 1;
    DS_STATUS = DS_STATUS_IRQ_PENDING;

    /* Boot console scanout mode. */
    TERM_FB_CTRL = 1u;
    SYS_COLOR_MODE = COLOR_MODE_8BIT;
    FB_MODE_SIZE = (FB_HEIGHT << 16) | FB_WIDTH;
    FB_MODE_STRIDE = FB_STRIDE;
    VIDEO_SCALER_MODE = VIDEO_SCALER_SLOT_DEFAULT_320X240;
    VIDEO_VTOTAL = VIDEO_VTOTAL_60HZ;

    /* Quiesce the sector engine register block. */
    DS_SLOT_ID = 0;
    DS_SLOT_OFFSET = 0;
    DS_BRIDGE_ADDR = 0;
    DS_LENGTH = 0;
    DS_PARAM_ADDR = 0;
    DS_RESP_ADDR = 0;

    /* Stop subsystems that can keep producing bus traffic or IRQs after a
     * warm restart. */
    MIX_CTRL = 0;
    for (uint32_t v = 0; v < 32u; v++)
        MIX_VOICE_CTRL(v) = 0;
    MIX_MASTER_VOL = 0xFFu;
    MIX_GROUP_VOL(0) = 0xFFu;
    MIX_GROUP_VOL(1) = 0xFFu;
    MIX_GROUP_VOL(2) = 0xFFu;
    MIX_GROUP_VOL(3) = 0xFFu;
    MIX_VOICE_GROUP_LO = 0;
    MIX_VOICE_GROUP_HI = 0;
    MIX_IRQ_CLEAR = 0xFFFFFFFFu;

    LINK_CTRL = BOOT_LINK_CTRL_RESET;

    BOOT_GPU_CTRL = BOOT_GPU_CTRL_SOFT_RESET;
    for (volatile int i = 0; i < 8; i++) {}
    uint32_t gpu_wait = BOOT_HW_IDLE_TIMEOUT;
    while (BOOT_GPU_STATUS & BOOT_GPU_STATUS_DMA_BUSY) {
        if (--gpu_wait == 0)
            break;
    }
    BOOT_GPU_DMA_SRC = 0;
    BOOT_GPU_DMA_LEN = 0;
    BOOT_GPU_TEX_FLUSH = 1;
    BOOT_GPU_CTRL = BOOT_GPU_CTRL_RING_RESET;
    for (volatile int i = 0; i < 8; i++) {}

    __asm__ volatile("fence" ::: "memory");
}

/* Image size: HPS_BOOT_LEN when sane, else the linked size. */
__attribute__((section(".text.boot")))
static uint32_t boot_os_image_size(void) {
    uint32_t linked_size = (uint32_t)(uintptr_t)_os_copy_size;
    uint32_t hps_size = HPS_BOOT_LEN;

    if (hps_size >= 4096u && hps_size <= BOOT_OS_SIZE_MAX)
        return hps_size;
    return linked_size;
}

/* CRC-32/ISO-HDLC over a loaded SDRAM range via the uncached alias. */
__attribute__((section(".text.boot")))
static uint32_t boot_crc32_uncached(uint32_t cached_base, uint32_t len) {
    volatile const uint32_t *p =
        (volatile const uint32_t *)boot_sdram_uncached_addr((void *)(uintptr_t)cached_base);
    uint32_t crc = 0xFFFFFFFFu;
    uint32_t words = len >> 2;
    for (uint32_t w = 0; w < words; w++) {
        uint32_t v = p[w];
        for (int b = 0; b < 4; b++) {
            crc ^= (v & 0xFFu);
            v >>= 8;
            for (int k = 0; k < 8; k++)
                crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1u)));
        }
    }
    for (uint32_t b = 0; b < (len & 3u); b++) {
        uint32_t v = p[words] >> (b * 8);
        crc ^= (v & 0xFFu);
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1u)));
    }
    return crc ^ 0xFFFFFFFFu;
}

__attribute__((section(".text.boot")))
static int boot_verify_os_image(uint32_t total) {
    if (total < OS_CRC_TRAILER_BYTES)
        return 1;
    uint32_t image_len = total - OS_CRC_TRAILER_BYTES;
    uint32_t base = (uint32_t)(uintptr_t)_osdata_init_vma_start;
    volatile const uint32_t *trailer =
        (volatile const uint32_t *)boot_sdram_uncached_addr(
            (void *)(uintptr_t)(base + image_len));
    if (trailer[0] != OS_CRC_MAGIC)
        return 1;   /* unstamped image — cannot verify */
    return boot_crc32_uncached(base, image_len) == trailer[1];
}

/* Image-carried entry + .bss bounds (OSE2 block — see the #define block
 * at the top for why this exists).  Fills the os_meta_* globals and
 * returns 1 when a plausible block is present; on any doubt returns 0
 * and the caller keeps the legacy baked symbols. */
volatile uint32_t __attribute__((section(".bss.boot"))) os_meta_entry;
volatile uint32_t __attribute__((section(".bss.boot"))) os_meta_bss_lo;
volatile uint32_t __attribute__((section(".bss.boot"))) os_meta_bss_hi;

__attribute__((section(".text.boot")))
static int boot_read_os_meta(uint32_t total) {
    os_meta_entry = 0;
    if (total < OS_CRC_TRAILER_BYTES + OS_META_BYTES)
        return 0;
    uint32_t base = (uint32_t)(uintptr_t)_osdata_init_vma_start;
    volatile const uint32_t *m =
        (volatile const uint32_t *)boot_sdram_uncached_addr(
            (void *)(uintptr_t)(base + total - OS_CRC_TRAILER_BYTES - OS_META_BYTES));
    if (m[0] != OS_META_MAGIC)
        return 0;
    uint32_t entry = m[1], lo = m[2], hi = m[3];
    /* Plausibility: entry inside the loaded image; .bss at/above the
     * image start, ordered, within the SDRAM PMA window. */
    if (entry < base || entry >= base + total)
        return 0;
    if (lo < base || hi < lo || hi > (OF_TARGET_SDRAM_BASE + OF_TARGET_SDRAM_SIZE))
        return 0;
    os_meta_entry  = entry;
    os_meta_bss_lo = lo;
    os_meta_bss_hi = hi;
    return 1;
}

/* Boot-ABI guard.  Returns 1 to proceed (id matches, or the image is
 * unstamped / the id is build-disabled), 0 to stop (id present and differs —
 * a wrong-target or stale mif+os.bin pair).  Reads the OABI block from the
 * loaded blob's tail ([OABI][OSE2][CRC]); the blob is raw-copied to
 * _osdata_init_vma_start, so the tail is readable even when the map is wrong. */
__attribute__((section(".text.boot")))
static int boot_check_os_abi(uint32_t total) {
    if ((uint32_t)OF_TARGET_BOOT_ABI == 0u)
        return 1;   /* no id injected at build time — check disabled */
    if (total < OS_CRC_TRAILER_BYTES + OS_META_BYTES + OS_ABI_BYTES)
        return 1;   /* too small to carry an OABI block — legacy image */
    uint32_t base = (uint32_t)(uintptr_t)_osdata_init_vma_start;
    volatile const uint32_t *a =
        (volatile const uint32_t *)boot_sdram_uncached_addr(
            (void *)(uintptr_t)(base + total - OS_CRC_TRAILER_BYTES
                                - OS_META_BYTES - OS_ABI_BYTES));
    if (a[0] != OS_ABI_MAGIC)
        return 1;   /* unstamped (no OABI) — don't enforce */
    return a[1] == (uint32_t)OF_TARGET_BOOT_ABI;
}

/* Copy os.bin from the ioctl staging region to its runtime VMA.  Both
 * sides go through the uncached alias: the staging bytes were DMA'd by
 * hps_bridge (never cached), and the destination must be visible to the
 * imminent instruction fetch without trusting a cache sweep. */
__attribute__((section(".text.boot")))
static void boot_copy_os_once(uint32_t total) {
    volatile const uint32_t *src = (volatile const uint32_t *)BOOT_STAGE_UNCACHED;
    volatile uint32_t *dst =
        (volatile uint32_t *)boot_sdram_uncached_addr(_osdata_init_vma_start);

    boot_dcache_inval_range(_osdata_init_vma_start, total);

    uint32_t words = (total + 3u) / 4u;
    for (uint32_t i = 0; i < words; i++)
        dst[i] = src[i];

    __asm__ volatile("fence" ::: "memory");
}

__attribute__((section(".text.boot")))
static int boot_load_os(uint32_t total) {
    for (int attempt = 0; attempt < OS_LOAD_MAX_ATTEMPTS; attempt++) {
        boot_copy_os_once(total);
        if (boot_verify_os_image(total))
            return 0;
        os_load_crc_retries++;
    }
    pd_dbg_info = 0xC0DE0000u | (os_load_crc_retries & 0xFFFFu);
    return 0;   /* proceed with the last copy rather than bricking boot */
}

/* ======================================================================
 * Main
 * ====================================================================== */

__attribute__((section(".text.boot")))
int main(void) {
    pd_dbg_stage = 1;

    boot_hw_stabilize();

    /* A soft reset can leave dirty D-cache lines from the previous run. */
    flush_dcache_evict();

    boot_palette_init();

    /* Clear terminal framebuffer (scanout reads it via term_fb_active=1). */
    {
        volatile uint32_t *p = (volatile uint32_t *)TERM_FB_BASE;
        for (int i = 0; i < (320 * 240) / 4; i++) p[i] = 0;
    }

#ifdef OF_SDRAM_DIAG
    boot_sdram_diag();          /* never returns */
#endif

    /* Self-tuning clock: probe SDRAM BEFORE anything depends on it.  On
     * an autotune core with a marginal module this never returns from
     * the first call (the fabric restarts us at 90 MHz); everywhere
     * else it costs ~40 ms.  Runs after the FB clear so its "90 MHz"
     * note isn't wiped. */
    boot_clk_autotune();

    boot_fb_puts(0, 0, "Waiting for boot.rom...");

    /* Wait for the HPS to deliver boot.rom.  The MiSTer main process
     * streams it right after loading the core, so this normally takes
     * tens of milliseconds; the long timeout covers slow SD cards. */
    pd_dbg_stage = 2;
    {
        unsigned int start_wait = SYS_CYCLE_LO;
        while (!(HPS_STATUS & HPS_STATUS_BOOT_LOADED)) {
            if ((SYS_CYCLE_LO - start_wait) > BOOT_ROM_WAIT_CYCLES) {
                boot_fb_clear_row(0);
                boot_fb_puts(0, 0, "No boot.rom from HPS");
                boot_fb_puts(0, 1, "Place boot.rom next to the core");
                while (!(HPS_STATUS & HPS_STATUS_BOOT_LOADED)) {}
                break;
            }
        }
    }

    boot_fb_clear_row(0);
    boot_fb_clear_row(1);
    boot_fb_puts(0, 0, "Loading...");

    pd_dbg_stage = 3;

    uint32_t os_size = boot_os_image_size();
    (void)boot_load_os(os_size);

    /* Backstop for the autotune probe: the bulk staging->VMA copy is the
     * heaviest SDRAM read pattern in the boot; if it exhausted its CRC
     * retries at 100 MHz on an autotune core, drop to 90 and redo the
     * whole boot (staging is intact — the copy never modifies it). */
    if (os_load_crc_retries >= OS_LOAD_MAX_ATTEMPTS) {
        uint32_t cc = HPS_CLK_CTRL;
        if ((cc & HPS_CLK_PRESENT) && !(cc & HPS_CLK_ATTEMPTED))
            boot_clk_request_switch();   /* never returns */
    }

    /* Refuse to run an os.bin whose memory map differs from this baked
     * bootloader (wrong target / stale mif): it would pass the content CRC
     * yet load+run at the wrong addresses (silent black).  Show why + stop. */
    if (!boot_check_os_abi(os_size)) {
        boot_fb_clear_row(0);
        boot_fb_clear_row(1);
        boot_fb_puts(0, 0, "BOOT ABI MISMATCH");
        boot_fb_puts(0, 1, "os.bin != this core's bootloader");
        boot_fb_puts(0, 2, "Rebuild firmware.mif (make firmware)");
        while (1) { }
    }

    pd_dbg_stage = 4;
    boot_fb_clear_row(0);

    /* .bss bounds and entry from the image's own OSE2 metadata when
     * present (os_meta_entry != 0) — the baked _os_bss_* / os_main
     * symbols only describe the kernel THIS bitstream was built with;
     * a swapped boot.rom with a shifted layout would otherwise get a
     * stale clear range and/or a stale entry jump (the boot lottery). */
    (void)boot_read_os_meta(os_size);

    /* LOUD fallback (2026-08-13): every modern os.bin is OSE2-stamped, so
     * "no meta at the computed offset" means the SIZE is wrong — on hardware
     * HPS_BOOT_LEN was found not delivering a sane value, the silent baked
     * fallback engaged, and any boot.rom whose layout differed from this
     * bitstream's build derailed into an unexplained black screen.  Falling
     * back is still the right move (it is what boots a matched pair), but it
     * must never be silent again: paint the sizes on screen and pause so a
     * mismatched pair is a readable message, not a lottery. */
    if (!os_meta_entry) {
        static const char hexd[] = "0123456789abcdef";
        char msg[22] = "meta miss h=";
        uint32_t v = HPS_BOOT_LEN;
        for (int i = 0; i < 8; i++)
            msg[12 + i] = hexd[(v >> (28 - 4 * i)) & 0xF];
        msg[20] = 0;
        boot_fb_puts(0, 0, msg);
        char msg2[22] = "using sz  u=";
        v = os_size;
        for (int i = 0; i < 8; i++)
            msg2[12 + i] = hexd[(v >> (28 - 4 * i)) & 0xF];
        msg2[20] = 0;
        boot_fb_puts(0, 1, msg2);
        for (volatile uint32_t spin = 0; spin < 300000000u; spin++) {}
    }
    {
    char *bss_lo = os_meta_entry ? (char *)(uintptr_t)os_meta_bss_lo
                                 : _os_bss_start;
    char *bss_hi = os_meta_entry ? (char *)(uintptr_t)os_meta_bss_hi
                                 : _os_bss_end;
    void (*os_entry_fn)(void) = os_meta_entry
                                 ? (void (*)(void))(uintptr_t)os_meta_entry
                                 : os_main;

    boot_dcache_inval_range(bss_lo, (uint32_t)(bss_hi - bss_lo));
    boot_dcache_inval_range((void *)(uintptr_t)(RUNTIME_STACK_TOP - RUNTIME_STACK_SIZE),
                            RUNTIME_STACK_SIZE);
    flush_icache();
    os_finalize_memory(bss_lo, bss_hi);
    boot_zero_uncached_sdram(RUNTIME_STACK_TOP - RUNTIME_STACK_SIZE,
                             RUNTIME_STACK_TOP);

    pd_dbg_stage = 5;

    if (os_load_crc_retries) {
        boot_fb_puts(0, 1, "OS reloaded (CRC) x");
        boot_fb_putchar(19, 1, '0' + (os_load_crc_retries & 7));
    }

    /* Jump to OS */
    switch_to_runtime_stack_and_call(os_entry_fn, _runtime_stack_top);
    }

    while (1) {}
    return 0;
}
