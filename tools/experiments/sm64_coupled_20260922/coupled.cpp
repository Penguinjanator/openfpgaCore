// Private hybrid simulation: qsim CPU timing + GPU/Pocket SDRAM RTL.
// CPU caches retain qsim's timing model; physical CPU traffic is optional
// sensitivity injection, not a replacement for a full CPU RTL simulation.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <map>
#include <string>
#include "Vtb_gpu_transluc.h"
#include "Vtb_gpu_transluc___024root.h"
#include "verilated.h"
extern "C" {
#include "env.h"
#include "cache.h"
#include "coupled.h"
}

static Vtb_gpu_transluc *tb;
static qenv *env;
static uint8_t *original_memory;
static bool active, initializing;
static uint64_t cycles, cpu_origin, time_origin_us, busy_cycles;
static uint64_t next_vblank, vblanks, presents, next_scan, scan_requests;
static uint64_t next_cpu, cpu_requests, next_audio, audio_requests;
static uint64_t rd_polls, fence_polls, publications;
static uint32_t ring_offset, last_fence, pending_token, last_submitted;
static int display_idx, pending_idx = -1, scan_enable = 1;
static int cpu_period, audio_period;
static bool scan_busy;
static FILE *events;
static std::string folder;
struct Frame { uint64_t submit = 0, finish = 0, present = 0; uint32_t tick = 0, idx = 0; };
static std::map<uint32_t, Frame> frames;
extern "C" { uint32_t coupled_audio_pc, coupled_render_pc; }
static bool sound_enabled;
static FILE *audio_events, *wav;
static std::deque<uint32_t> audio_fifo;
static uint64_t audio_samples, audio_underruns, mix_reads, audio_ticks, voice_commits;
static uint64_t next_sample;
static void transfer_voices();
static void finish_wav();

static uint64_t cpu_time() { return env->cpu->model->cyc - cpu_origin; }
static void event(const char *kind, uint32_t token, int idx) {
    if (!events) return;
    auto f = frames.find(token);
    fprintf(events, "%s,%llu,%u,%u,%d\n", kind, (unsigned long long)cycles,
            f == frames.end() ? 0 : f->second.tick, token, idx);
    fflush(events);
}
static uint8_t *memory() {
    return reinterpret_cast<uint8_t *>(&tb->rootp->tb_gpu_transluc__DOT__sdram_chip__DOT__mem[0]);
}
static uint32_t reg_read(unsigned r) { tb->reg_addr = r; tb->eval(); return tb->reg_rdata; }

static void tick() {
    tb->clk = 0; tb->eval();
    if (!initializing) {
        if (cycles >= next_vblank) {
            vblanks++;
            if (pending_idx >= 0) {
                display_idx = pending_idx;
                pending_idx = -1;
                presents++;
                frames[pending_token].present = cycles;
                event("present", pending_token, display_idx);
            }
            next_vblank = ((vblanks + 1) * 100000000ull + 59) / 60 - time_origin_us * 100;
        }
        tb->slave_swap_pending = pending_idx >= 0;
        if (sound_enabled) {
            if (cycles >= next_sample) {
                uint32_t value = 0;
                if (!audio_fifo.empty()) { value=audio_fifo.front(); audio_fifo.pop_front(); }
                else if (cycles >= 2000000) audio_underruns++; // exclude first 20 ms of FIFO handoff
                int16_t samples[2] = {(int16_t)(value>>16), (int16_t)value};
                fwrite(samples, sizeof samples, 1, wav);
                audio_samples++;
                next_sample = (audio_samples * 100000000ull + 47999) / 48000;
            }
            tb->mix_fifo_level = audio_fifo.size();
        }
        tb->inj_burst_rd = 0;
        if (scan_busy && tb->inj_burst_data_done) scan_busy = false;
        if (scan_enable && !scan_busy && cycles >= next_scan) {
            tb->inj_burst_rd = 1;
            // Same conservative 262-active-line injection as prior RTL tests.
            tb->inj_burst_addr = (uint32_t(display_idx) << 20) + ((scan_requests % 240) * 640);
            tb->inj_burst_len = 160;
            scan_busy = true; scan_requests++;
            next_scan = cycles + 6361;
        }
        if (cpu_period && !tb->m1_arvalid && cycles >= next_cpu) {
            tb->m1_arvalid = 1; tb->m1_araddr = 0x12000000 + ((cpu_requests * 64) & 0x1fffff);
            tb->m1_arlen = 15;
        }
        if (audio_period && !tb->m3_arvalid && cycles >= next_audio) {
            tb->m3_arvalid = 1; tb->m3_araddr = 0x13800000 + ((audio_requests * 64) & 0x3ffff);
            tb->m3_arlen = 15;
        }
        tb->eval();
        if (tb->trace_wr_take) {
            uint32_t a = tb->trace_wr_addr & 0x03ffffff;
            unsigned idx = a >> 20;
            if (idx < 3 && (a & 0xfffff) < 320*240*2 &&
                ((int)idx == display_idx || (int)idx == pending_idx)) {
                fprintf(stderr,"GPU writes displayed/pending framebuffer %u at cycle %llu\n",idx,(unsigned long long)cycles);
                abort();
            }
        }
    }
    bool ctake = tb->m1_arvalid && tb->m1_arready;
    bool atake = tb->m3_arvalid && tb->m3_arready;
    bool mtake = tb->mix_read_take;
    tb->clk = 1; tb->eval();
    cycles++;
    if (ctake) { tb->m1_arvalid = 0; next_cpu = cycles + cpu_period; cpu_requests++; }
    if (atake) { tb->m3_arvalid = 0; next_audio = cycles + audio_period; audio_requests++; }
    if (!initializing) {
        if (sound_enabled && tb->mix_sample_wr) audio_fifo.push_back(tb->mix_sample_data);
        if (mtake) mix_reads++;
        assert(audio_fifo.size() < 1024);
        busy_cycles += bool(tb->busy);
        if (tb->gpu_swap_req) {
            if (pending_idx >= 0) { fprintf(stderr,"overwrite pending swap\n"); abort(); }
            pending_idx = tb->gpu_swap_idx;
            pending_token = tb->fence_reached;
            if (pending_idx == display_idx) { fprintf(stderr,"drawing displayed buffer\n"); abort(); }
            auto &f = frames[pending_token];
            f.finish = cycles;
            event("complete", pending_token, pending_idx);
            char path[4096];
            snprintf(path, sizeof path, "%s/frame-tick-%05u-token-%05u.bin", folder.c_str(), f.tick, pending_token);
            FILE *out = fopen(path,"wb");
            if (!out) abort();
            fwrite(memory() + (uint32_t(pending_idx) << 20), 1, 320*240*2, out);
            fclose(out);
        }
        if (tb->fence_reached != last_fence) {
            last_fence = tb->fence_reached;
            event("fence", last_fence, pending_idx);
        }
        if (tb->dbg_mem_errors) { fprintf(stderr,"SDRAM protocol errors %x\n",tb->dbg_mem_errors); abort(); }
    }
}
static void advance(uint64_t to) { while (cycles < to) tick(); }
static void reg_write(unsigned r, uint32_t v) {
    tb->reg_wr = 1; tb->reg_addr = r; tb->reg_wdata = v;
    tick(); tb->reg_wr = 0;
}

extern "C" int coupled_active() { return active; }
extern "C" void coupled_sync() {
    if (!active) return;
    advance(cpu_time());
    env->hw_display = env->buf_display = display_idx;
    env->buf_ready = pending_idx;
    env->swap_kicked = pending_idx >= 0;
}
extern "C" uint64_t coupled_time_us() {
    coupled_sync();
    return time_origin_us + cpu_time() / 100;
}
extern "C" void coupled_start(void *p, const char *out) {
    auto E = static_cast<qenv *>(p);
    if (!coupled_audio_pc) {
        const qsim_sym *s = qsim_syms_lookup(&E->syms,"of_voice_sync");
        if (s) coupled_audio_pc = s->addr;
        if (getenv("COUPLED_RENDER_PC")) coupled_render_pc = strtoul(getenv("COUPLED_RENDER_PC"),nullptr,0);
    }
    if (active || !getenv("COUPLED_START_FRAME")) return;
    if (E->flips < strtoull(getenv("COUPLED_START_FRAME"), nullptr, 0)) return;
    assert(E->cpu->model && !E->lint && E->gpu);
    env = E; folder = out;
    events = fopen((folder+"/events.csv").c_str(), "w");
    if (!events) abort();
    fprintf(events,"kind,cycle,game_tick,token,buffer\n");
    uint32_t old_rd = gpu_mmio_read(E->gpu, 0x10);
    uint32_t old_fence = gpu_fence_reached(E->gpu);
    assert(!gpu_queued_words(E->gpu));
    initializing = true;
    tb = new Vtb_gpu_transluc;
    sound_enabled = getenv("COUPLED_SOUND");
    tb->mix_enable = tb->mix_wr = tb->mix_irq_clear_wr = 0;
    tb->mix_fifo_level=0;
    tb->aggr_en = 1; tb->m1_arvalid = tb->m1_awvalid = tb->m1_wvalid = 0; tb->m1_rready = 1;
    tb->m2_arvalid = tb->m2_awvalid = tb->m2_wvalid = 0; tb->m2_rready = 1;
    tb->m3_arvalid = 0; tb->m3_rready = 1; tb->inj_burst_rd = 0;
    tb->ss1_dqm_mode = tb->ss1_read_dqm = tb->ss1_read_delay = 0;
    tb->slave_swap_pending = 0;
    tb->reset_n = 0; tb->reg_wr = 0; tb->bd_we = 0;
    for (int i=0;i<20;i++) tick();
    tb->reset_n = 1;
    for (int i=0;i<30000;i++) tick();
    reg_write(0,4); reg_write(0,1); reg_write(12,gpu_mmio_read(E->gpu,0x30));
    reg_write(0,16); reg_write(10,1);
    for (int i=0;i<2000;i++) tick();
    reg_write(1,0x02000001); reg_write(1,old_fence); reg_write(0,8);
    for (int i=0;i<1000;i++) tick();
    assert(tb->fence_reached == old_fence && !tb->busy);
    ring_offset = (old_rd - reg_read(4)) & 16383;
    original_memory = E->cpu->sdram;
    memcpy(memory(), original_memory, E->cpu->sdram_size);
    E->cpu->sdram = E->scan = memory();
    if (sound_enabled) transfer_voices();
    cpu_origin = E->cpu->model->cyc;
    time_origin_us = 5000000 + (E->flips * 1000000ull + 29) / 30;
    display_idx = E->hw_display;
    last_fence = old_fence;
    cycles = busy_cycles = 0;
    vblanks = time_origin_us * 60 / 1000000;
    next_vblank = ((vblanks+1)*100000000ull+59)/60 - time_origin_us*100;
    scan_enable = !getenv("COUPLED_NO_SCANOUT");
    cpu_period = getenv("COUPLED_CPU_PERIOD") ? atoi(getenv("COUPLED_CPU_PERIOD")) : 0;
    audio_period = getenv("COUPLED_AUDIO_PERIOD") ? atoi(getenv("COUPLED_AUDIO_PERIOD")) : 0;
    if (sound_enabled) {
        assert(audio_period == 0);
        audio_events = fopen((folder+"/audio-events.csv").c_str(),"w");
        wav = fopen((folder+"/audio.wav").c_str(),"wb");
        assert(audio_events && wav);
        fprintf(audio_events,"kind,cycle,voice,rate,vol_left,vol_right\n");
        uint8_t blank[44]={0}; fwrite(blank,1,44,wav);
        tb->mix_enable=1;
    }
    initializing = false; active = true;
    fprintf(stderr,"coupled: start at frame %llu, 100 MHz; CPU period=%d audio period=%d scanout=%d\n",
            (unsigned long long)E->flips,cpu_period,audio_period,scan_enable);
}
extern "C" uint32_t coupled_read(uint32_t off) {
    coupled_sync();
    uint32_t v = reg_read(off/4);
    if (off == 0x04 || off == 0x10) v = (v + ring_offset) & 16383;
    if (off == 0x10) rd_polls++;
    if (off == 0x18) fence_polls++;
    return v;
}
extern "C" void coupled_write(uint32_t off, uint32_t value) {
    uint64_t to = cpu_time();
    if (to > cycles) advance(to-1);
    else env->cpu->model->cyc++;
    reg_write(off/4,value);
    if (off == 0 && (value & 8)) publications++;
    if ((reg_read(5) & 0x300) != 0x100) { fprintf(stderr,"RTL ring overflow or lost mode\n"); abort(); }
}
extern "C" void coupled_submit(uint32_t idx, uint32_t token, uint32_t game_tick) {
    if (!active) return;
    coupled_sync();
    frames[token] = Frame{cycles,0,0,game_tick,idx};
    last_submitted = token;
    event("submit",token,idx);
}
extern "C" int coupled_acquire(int just, uint32_t token) {
    coupled_sync();
    if (just < 0) return env->buf_draw;
    assert((int32_t)(tb->fence_reached-token) >= 0);
    for (int i=0;i<3;i++) if(i!=display_idx && i!=pending_idx) { env->buf_draw=i; return i; }
    abort();
}
extern "C" void coupled_video_timing(uint32_t addr) {
    coupled_sync();
    uint32_t words[8] = {(uint32_t)vblanks,(uint32_t)presents,0,0,0,0,0,0};
    auto p = qsim_mem_ptr(env->cpu,addr,sizeof words);
    assert(p); memcpy(p,words,sizeof words);
}
extern "C" void coupled_finish() {
    if (!active) return;
    coupled_sync();
    uint64_t stop = cycles + 100000000;
    while ((tb->busy || pending_idx>=0 || (int32_t)(tb->fence_reached-last_submitted)<0) && cycles < stop) tick();
    assert(cycles < stop);
    FILE *out = fopen((folder+"/coupled.json").c_str(),"w");
    assert(out);
    fprintf(out,"{\n  \"cycles\": %llu, \"cpu_cycles\": %llu, \"busy_cycles\": %llu,\n"
                "  \"presented\": %llu, \"frames\": %zu, \"rdptr_polls\": %llu, \"fence_polls\": %llu,\n"
                "  \"publications\": %llu, \"scan_requests\": %llu, \"cpu_requests\": %llu, \"audio_requests\": %llu,\n"
                "  \"memory_errors\": %u, \"clock_hz\": 100000000,\n"
                "  \"audio_ticks\": %llu, \"voice_commits\": %llu, \"audio_samples\": %llu,\n"
                "  \"audio_underruns_after_20ms\": %llu, \"mixer_reads\": %llu\n}\n",
            (unsigned long long)cycles,(unsigned long long)cpu_time(),(unsigned long long)busy_cycles,
            (unsigned long long)presents,frames.size(),(unsigned long long)rd_polls,(unsigned long long)fence_polls,
            (unsigned long long)publications,(unsigned long long)scan_requests,
            (unsigned long long)cpu_requests,(unsigned long long)audio_requests,tb->dbg_mem_errors,
            (unsigned long long)audio_ticks,(unsigned long long)voice_commits,(unsigned long long)audio_samples,
            (unsigned long long)audio_underruns,(unsigned long long)mix_reads);
    fclose(out); fflush(events);
    if (sound_enabled) { fflush(audio_events); finish_wav(); }
}
extern "C" void coupled_close() {
    if (!active) return;
    env->cpu->sdram = original_memory;
    env->scan = original_memory;
    fclose(events);
    if (audio_events) fclose(audio_events);
    if (wav) fclose(wav);
    tb->final(); delete tb; tb=nullptr;
    active=false;
}
#include "audio.inc"
