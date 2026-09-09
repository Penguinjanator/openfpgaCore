/* Interrupt interleavings and delayed hardware acknowledgement in the real HAL. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include MIXER_SOURCE

static uint32_t registers[0x900 / 4], pending_ends, clear_bits;
static unsigned irq_enabled = 8, boundary_count, inject_at;
static int interrupt_pending, flush_interrupt, in_interrupt;
static int check_stopped_writes;
static of_mixer_handle_t interrupt_handle;
static const uint8_t *const cached_pcm = (void *)(uintptr_t)(OF_TARGET_SDRAM_BASE + 0x100000);
static const uint8_t *const music_pcm = (void *)(uintptr_t)(OF_TARGET_SDRAM_UNCACHED_BASE + 0x200000);

static void settle_clear(void)
{
    pending_ends &= ~clear_bits;
    clear_bits = 0;
}

static void deliver_interrupt(void)
{
    if (!irq_enabled || !interrupt_pending || in_interrupt) return;
    interrupt_pending = 0;
    in_interrupt = 1;
    unsigned saved = irq_enabled;
    irq_enabled = 0;
    interrupt_handle = of_mixer_alloc_for_group_h(OF_MIXER_GROUP_MUSIC, music_pcm, 64, 22050, 1, 100);
    assert(!irq_enabled); /* HAL calls must preserve disabled entry state. */
    irq_enabled = saved;
    in_interrupt = 0;
}

static void boundary(void)
{
    settle_clear();
    if (in_interrupt) return;
    if (++boundary_count == inject_at) interrupt_pending = 1;
    deliver_interrupt();
}

static uint32_t test_irq_save(void)
{
    boundary();
    uint32_t saved = irq_enabled;
    irq_enabled = 0;
    return saved;
}

static void test_irq_restore(uint32_t prev)
{
    if (prev) irq_enabled = 8;
    boundary();
}

static volatile uint32_t *test_reg(unsigned offset)
{
    assert(offset < sizeof(registers) && !(offset & 3));
    boundary();
    if (check_stopped_writes && offset < 0x800 && (offset & 63) < 8)
        assert(!(registers[((offset & ~63u) + 12) / 4] & 1));
    return &registers[offset / 4];
}

static volatile uint32_t *test_pending(void) { boundary(); return &pending_ends; }
static volatile uint32_t *test_clear(void) { boundary(); return &clear_bits; }

void of_cache_flush_range(void *ptr, uint32_t bytes)
{
    assert(ptr == cached_pcm && bytes == 128);
    if (flush_interrupt) {
        /* A main-thread sample flush must not mask timer ticks. */
        assert(irq_enabled);
        flush_interrupt = 0;
        interrupt_pending = 1;
    }
    boundary();
}

static void reset(void)
{
    inject_at = boundary_count = 0;
    interrupt_pending = flush_interrupt = in_interrupt = 0;
    check_stopped_writes = 0;
    interrupt_handle = 0;
    irq_enabled = 8;
    memset(registers, 0, sizeof(registers));
    pending_ends = clear_bits = 0;
    of_mixer_init(32, 48000);
    settle_clear();
    boundary_count = 0;
}

static of_mixer_handle_t play(int group, int priority)
{
    return of_mixer_alloc_for_group_h(group, music_pcm, 64, 22050, priority, 100);
}

static void assert_groups(void)
{
    for (int i = 0; i < 32; ++i) {
        uint32_t packed = registers[(i < 16 ? 0x814 : 0x818) / 4];
        assert(((packed >> (2 * (i & 15))) & 3) == group_shadow[i]);
    }
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    reset();
    if (!strcmp(argv[1], "alloc")) {
        flush_interrupt = 1;
        of_mixer_handle_t main_handle = of_mixer_play_h(cached_pcm, 64, 48000, 100, 200);
        assert(main_handle && interrupt_handle);
        assert(of_mixer_handle_active(main_handle));
        assert(of_mixer_handle_active(interrupt_handle));
        assert((main_handle & 255) != (interrupt_handle & 255));
        assert_groups();
    } else if (!strcmp(argv[1], "grouped")) {
        of_mixer_handle_t occupied[31];
        for (int i = 0; i < 31; ++i) occupied[i] = play(OF_MIXER_GROUP_SFX, 100);
        of_mixer_stop_h(occupied[15]);
        registers[0x830 / 4] = active_shadow;
        flush_interrupt = 1;
        of_mixer_handle_t h = of_mixer_alloc_for_group_h(0, cached_pcm, 64, 48000, 100, 200);
        assert(h && of_mixer_handle_active(h));
        /* A higher-priority SFX may legitimately steal the newly allocated note. */
        for (int i = 0; i < 31; ++i)
            if (i != 15) assert(of_mixer_handle_active(occupied[i]));
        assert_groups();
    } else if (!strcmp(argv[1], "lag")) {
        of_mixer_handle_t handles[31];
        for (int i = 0; i < 31; ++i) handles[i] = play(1, 1);
        assert(registers[0x830 / 4] == 0); /* HW has not consumed the starts. */
        assert(play(1, 1) == OF_MIXER_HANDLE_INVALID);
        for (int i = 0; i < 31; ++i) assert(of_mixer_handle_active(handles[i]));
        assert(!(active_shadow & (1u << 31)));
    } else if (!strcmp(argv[1], "groups")) {
        of_mixer_handle_t h = play(1, 1);
        of_mixer_stop_h(h);
        assert(of_mixer_play_h(music_pcm, 64, 48000, 100, 200));
        assert_groups();
    } else if (!strcmp(argv[1], "retrigger")) {
        of_mixer_handle_t old = play(1, 1);
        flush_interrupt = 1;
        of_mixer_handle_t h = of_mixer_retrigger_h(old, cached_pcm, 64, 48000, 200);
        assert(h && h != old && of_mixer_handle_active(h));
        assert(!of_mixer_handle_active(old));
        assert(of_mixer_handle_active(interrupt_handle));
        assert((h & 255) != (interrupt_handle & 255));
    } else if (!strcmp(argv[1], "retrigger-stolen")) {
        of_mixer_handle_t old = play(1, 0);
        for (int i = 1; i < 31; ++i) assert(play(1, 1));
        registers[0x830 / 4] = active_shadow;
        flush_interrupt = 1;
        assert(!of_mixer_retrigger_h(old, cached_pcm, 64, 48000, 200));
        assert(of_mixer_handle_active(interrupt_handle));
        unsigned voice = interrupt_handle & 255;
        assert(registers[(voice * 64) / 4] == OF_TARGET_SDRAM_BASE + 0x200000);
    } else if (!strcmp(argv[1], "invalid")) {
        of_mixer_handle_t old = play(1, 1);
        assert(!of_mixer_retrigger_h(old, NULL, 64, 48000, 200));
        assert(of_mixer_handle_active(old));
        assert(!of_mixer_alloc_for_group_h(3, (void *)1, 64, 48000, 100, 200));
        assert(!of_mixer_alloc_for_group_h(3, music_pcm, UINT32_MAX, 48000, 100, 200));
        assert(group_shadow[30] == 0);
        assert_groups();
    } else if (!strcmp(argv[1], "ended")) {
        of_mixer_handle_t old = play(1, 1), ended[2];
        pending_ends = 1u << (old & 255);
        of_mixer_handle_t h = of_mixer_retrigger_h(old, music_pcm, 64, 48000, 100);
        assert(h && of_mixer_handle_active(h));
        assert(of_mixer_poll_ended_h(ended, 2) == 0);
        pending_ends = 1u << (h & 255);
        assert(of_mixer_poll_ended_h(ended, 2) == 1 && ended[0] == h);
        assert(!of_mixer_handle_active(h));
        of_mixer_handle_t next = play(1, 1);
        of_mixer_stop_h(h);
        assert(of_mixer_handle_active(next));
    } else if (!strcmp(argv[1], "play-stop")) {
        for (int i = 0; i < 31; ++i) assert(play(1, 1));
        check_stopped_writes = 1;
        assert(play(0, 100));
    } else if (!strcmp(argv[1], "retrigger-stop")) {
        of_mixer_handle_t h = play(1, 1);
        check_stopped_writes = 1;
        assert(of_mixer_retrigger_h(h, music_pcm, 64, 48000, 100));
    } else if (!strcmp(argv[1], "boundaries")) {
        for (int mode = 0; mode < 4; ++mode) {
            for (unsigned event = 1; event <= 60; ++event) {
                reset();
                of_mixer_handle_t old = mode == 3 ? play(1, 1) : 0;
                boundary_count = 0;
                inject_at = event;
                of_mixer_handle_t h = 0;
                if (mode == 0) h = of_mixer_play_h(cached_pcm, 64, 48000, 100, 200);
                if (mode == 1) h = of_mixer_alloc_for_group_h(0, cached_pcm, 64, 48000, 100, 200);
                if (mode == 2) of_mixer_set_group(30, 3);
                if (mode == 3) h = of_mixer_retrigger_h(old, cached_pcm, 64, 48000, 200);
                inject_at = 0;
                if (mode != 2) assert(h && of_mixer_handle_active(h));
                if (interrupt_handle) {
                    assert(of_mixer_handle_active(interrupt_handle));
                    if (h) assert((h & 255) != (interrupt_handle & 255));
                }
                assert(irq_enabled == 8);
                assert_groups();
            }
        }
    } else assert(0);
    puts("PASS");
    return 0;
}
