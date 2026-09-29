#!/usr/bin/env python3
"""Build a private qsim CPU + GPU/SDRAM RTL simulation."""
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT/'build/sm64-coupled-20260922'

def replace(s, old, new):
    assert s.count(old) == 1, (old[:80], s.count(old))
    return s.replace(old, new, 1)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    q = OUT/'qsim'; q.mkdir(exist_ok=True)
    for p in (ROOT/'build/sm64-schedule-20260922/qsim').iterdir():
        if p.is_file() and (p.suffix in ('.c','.h') or p.name == 'Makefile'):
            shutil.copy2(p, q/p.name)
    shutil.copy2(HERE/'coupled.h', q/'coupled.h')
    s = (q/'env.c').read_text().replace('#include "env.h"', '#include "env.h"\n#include "coupled.h"', 1)
    s = replace(s, '    if (E->sm64_profile) {\n        /* Profiling clock',
                '    if (coupled_active()) return coupled_time_us();\n'
                '    if (E->sm64_profile) {\n        /* Profiling clock')
    s = replace(s, '    E->hw_display = idx & 3;', '    if (!coupled_active()) E->hw_display = idx & 3;')
    s = replace(s, '    schedule_published_frames++;',
                '    coupled_submit(p[0], p[1], rd32(E, E->host_framecount_addr));\n'
                '    schedule_published_frames++;')
    s = replace(s, '        if (E->gpu) v = gpu_mmio_read(E->gpu, off & ~3u);',
                '        if (coupled_active()) v = coupled_read(off & ~3u);\n'
                '        else if (E->gpu) v = gpu_mmio_read(E->gpu, off & ~3u);')
    s = replace(s, '        if (E->gpu) {\n            if (E->vec_nframes)',
                '        if (coupled_active()) coupled_write(off, val);\n'
                '        if (E->gpu) {\n            if (E->vec_nframes)')
    s = replace(s, '        uint64_t cyc = cpu->instret_live * ENV_SYSREG_CYC_PER_INSN;',
                '        uint64_t cyc = coupled_active() ? coupled_time_us() * 100u : cpu->instret_live * ENV_SYSREG_CYC_PER_INSN;')
    s = replace(s, '    E->svc_calls[i]++;', '    coupled_sync();\n    E->svc_calls[i]++;')
    s = replace(s, 'if (E->sm64_profile && E->sm64_sound_addr) gzero',
                'if (E->sm64_profile && E->sm64_sound_addr && !getenv("COUPLED_SOUND")) gzero')
    s = replace(s, '    switch (i) {\n    case 0:',
                '    if (coupled_audio_service(E, i, &r0)) {\n'
                '        x[10] = r0; cpu->pc = x[1]; return QSIM_TRAP_RESUME;\n    }\n'
                '    switch (i) {\n    case 0:')
    s = replace(s, '        int just = (int32_t)a0;',
                '        if (coupled_active()) { r0 = coupled_acquire((int32_t)a0, a1); break; }\n'
                '        int just = (int32_t)a0;')
    s = replace(s, '        gzero(E, a0, 32);',
                '        if (coupled_active()) { coupled_video_timing(a0); break; }\n'
                '        gzero(E, a0, 32);')
    s = replace(s, 'void env_free(qenv *E)\n{', 'void env_free(qenv *E)\n{\n    coupled_close();')
    (q/'env.c').write_text(s)
    s = (q/'main.c').read_text().replace('#include "env.h"', '#include "env.h"\n#include "coupled.h"', 1)
    s = replace(s, '    for (;;) {\n        uint64_t left = max_insns',
                '    for (;;) {\n        coupled_start(&E, out);\n        uint64_t left = max_insns')
    s = replace(s, '    clock_gettime(CLOCK_MONOTONIC, &t1);\n    double wall',
                '    coupled_finish();\n    clock_gettime(CLOCK_MONOTONIC, &t1);\n    double wall')
    (q/'main.c').write_text(s)
    s = (q/'cpu.c').read_text()
    s = '#include "coupled.h"\n' + s
    (q/'cpu.c').write_text(s)
    s = (q/'cpu_exec.h').read_text()
    s = replace(s, '        size_t _ti = (size_t)((te) - arena);',
                '        if ((tpc) == coupled_audio_pc || (tpc) == coupled_render_pc) coupled_enter(tpc); \\\n        size_t _ti = (size_t)((te) - arena);')
    s = replace(s, '            memcpy(sd_uc + _o, &_t, sizeof _t);',
                '            coupled_sync(); \\\n            memcpy(sd_uc + _o, &_t, sizeof _t);')
    (q/'cpu_exec.h').write_text(s)
    sources = 'cpu fpu cache prof qelf lint gpu app env main'.split()
    subprocess.run(['make','-j3',*[f'build/qsim/{n}.o' for n in sources]], cwd=q, check=True)
    frozen = OUT/'frozen'
    shutil.copytree(ROOT/'build/sm64-estimates-20260922/memory/frozen', frozen, dirs_exist_ok=True)
    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()
    s = replace(s, '    output wire [31:0] dbg_aux,',
                '    input wire slave_swap_pending,\n    output wire gpu_swap_req,\n'
                '    output wire [1:0] gpu_swap_idx,\n    output wire [31:0] dbg_aux,')
    s = s.replace('wire        gpu_swap_req;','').replace('wire [1:0]  gpu_swap_idx;','')
    s = replace(s, ".slave_swap_pending(1'b0)", '.slave_swap_pending(slave_swap_pending)')
    s = replace(s, '    input wire slave_swap_pending,', '''    input wire mix_enable, mix_wr, mix_irq_clear_wr,
    input wire [3:0] mix_field,
    input wire [4:0] mix_sel,
    input wire [31:0] mix_data, mix_irq_clear,
    input wire [9:0] mix_fifo_level,
    output wire mix_ready, mix_sample_wr, mix_read_take,
    output wire [31:0] mix_sample_data, mix_ended, mix_active,
    input wire slave_swap_pending,''')
    s = replace(s, '// SRAM scratch', '''wire mix_arvalid, mix_rready;
wire [31:0] mix_araddr;
wire [7:0] mix_arlen;
assign mix_read_take = mix_enable && mix_arvalid && m3_arready;
audio_mixer audio (
    .clk(clk), .reset_n(reset_n), .mixer_enable(mix_enable),
    .voice_wr(mix_wr), .voice_wr_ready(mix_ready), .voice_field(mix_field),
    .voice_sel(mix_sel), .voice_sel_rd(mix_sel), .voice_wdata(mix_data),
    .master_vol(8'd255), .group_vol_0(8'd255), .group_vol_1(8'd255),
    .group_vol_2(8'd255), .group_vol_3(8'd255), .voice_group_packed(64'd0),
    .m_arvalid(mix_arvalid), .m_arready(m3_arready), .m_araddr(mix_araddr), .m_arlen(mix_arlen),
    .m_rvalid(m3_rvalid), .m_rdata(m3_rdata), .m_rresp(2'b0), .m_rlast(m3_rlast), .m_rready(mix_rready),
    .sample_wr(mix_sample_wr), .sample_data(mix_sample_data), .fifo_level(mix_fifo_level),
    .pos_readback(), .irq_clear_wr(mix_irq_clear_wr), .irq_clear(mix_irq_clear),
    .voice_end_pending(mix_ended), .voice_end_irq(), .voice_active_mask(mix_active)
);
// SRAM scratch''')
    for old, new in [('aggr_en & m3_arvalid', 'aggr_en & (mix_enable ? mix_arvalid : m3_arvalid)'),
                     ('.m3_araddr(m3_araddr)', '.m3_araddr(mix_enable ? mix_araddr : m3_araddr)'),
                     ('.m3_arlen(m3_arlen)', '.m3_arlen(mix_enable ? mix_arlen : m3_arlen)'),
                     ('.m3_rready(m3_rready)', '.m3_rready(mix_enable ? mix_rready : m3_rready)')]:
        s = replace(s, old, new)
    top.write_text(s)
    cfg = json.loads((ROOT/'build/sm64-estimates-20260922/memory/config.json').read_text())['gpu']
    rtl = [top, frozen/'sdram_model_full.v', frozen/'altsyncram_stub.v',
           *[frozen/'common'/n for n in ['gpu_core.v','gpu_edge_walker.v','gpu_tex_cache.v',
                                        'axi_sdram_arbiter.v','sync_fifo.v','axi_sdram_slave.v','audio_mixer.v']],
           frozen/'synch_3.v', frozen/'io_sdram_pocket_test.v', HERE/'coupled.cpp']
    objs = [str(q/'build/qsim'/f'{n}.o') for n in sources]
    cmd = ['verilator','--cc','--exe','--build','-j','3','-Wno-fatal','-Wno-BADVLTPRAGMA',
           '--top-module','tb_gpu_transluc','--Mdir',str(OUT/'obj'),'-I'+str(frozen/'common'),
           '-CFLAGS','-std=c++17 -O2 -I'+str(q),'-LDFLAGS',' '.join(objs)+' -lm',
           *['+define+'+d for d in cfg['variant']['defs'].split()], *map(str,rtl)]
    (OUT/'build-command.json').write_text(json.dumps(cmd, indent=2)+'\n')
    with (OUT/'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    print(OUT/'obj/Vtb_gpu_transluc')

if __name__ == '__main__': main()
