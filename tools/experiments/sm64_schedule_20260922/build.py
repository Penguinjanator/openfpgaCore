#!/usr/bin/env python3
"""Build private SM64 scheduling overlays; never modify sibling repositories."""
import difflib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'build/sm64-schedule-20260922'
SM = ROOT.parent / 'SM64/src/sm64'

def replace(s, old, new):
    assert s.count(old) == 1, (old[:90], s.count(old))
    return s.replace(old, new, 1)

def main(label):
    assert label in ('control', 'prepare', 'prepare_small', 'prepare_capture', 'audio', 'combined')
    prep = label in ('prepare', 'prepare_small', 'prepare_capture', 'combined')
    audio = label in ('audio', 'combined')
    OUT.mkdir(parents=True, exist_ok=True)
    inc = OUT / 'include'
    inc.mkdir(exist_ok=True)
    helper = (ROOT/'tools/experiments/sm64_renderer_20260922/build_overlay.py').read_text()
    helper = helper.replace("'-I'+str(sdk/'include')", "'-I'+str(out/'include'),'-I'+str(sdk/'include')")
    (OUT/'build_overlay.py').write_text(helper)
    spec = importlib.util.spec_from_file_location('schedule_overlay', OUT/'build_overlay.py')
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    header = (ROOT/'src/firmware/api/of_gpu.h').read_text()
    if prep:
        header = replace(header, 'static inline void _gpu_flush_cmd_stream(void) {',
            'static inline void _gpu_flush_cmd_stream(void) {\n'
            '    if (sm64_preparing) { gpu_prepare_flush(0); return; }\n'
            '    gpu_prepare_publish(_gpu_batch_buf, _gpu_cmd_words);')
        header = replace(header, 'static inline void _gpu_stream_reserve_words(uint32_t words) {',
            'static inline void _gpu_stream_reserve_words(uint32_t words) {\n'
            '    if (sm64_preparing) {\n'
            '        if (words <= SM64_PREP_WORDS - _gpu_cmd_words) return;\n'
            '        sm64_prepare_capacity_flushes++;\n'
            '        gpu_prepare_flush(1);\n'
            '    }')
        header = replace(header,
            'if (_gpu_batch_buf == NULL || _gpu_cmd_words >= OF_GPU_COMMAND_STREAM_BATCH_WORDS)',
            'if (_gpu_batch_buf == NULL || _gpu_cmd_words >= '
            '(sm64_preparing ? SM64_PREP_WORDS : OF_GPU_COMMAND_STREAM_BATCH_WORDS))')
    (inc/'of_gpu.h').write_text(header)
    (inc/'audio_clock.h').write_text((HERE/'audio_clock.h').read_text())
    paths = {n: SM/'sm64/src/pc/gfx'/n for n in ('gfx_gpu.c','gfx_pc.c')}
    paths['wm_pocket.c'] = SM/'pocket/wm_pocket.c'
    old = {n:p.read_text() for n,p in paths.items()}
    gpu, pc, wm = (old[n] for n in ('gfx_gpu.c','gfx_pc.c','wm_pocket.c'))
    prefix = 'extern void sm64_audio_service(void);\n'
    if label == 'prepare_capture': prefix += '#define SM64_PREP_CAPTURE_TEST 1\n'
    if audio: prefix += '#define OF_GPU_WAIT_HOOK() sm64_audio_service()\n'
    if prep:
        prefix += '#define SM64_PREP_WORDS '+('512u' if label=='prepare_small' else '32768u')+'\n'
        prefix += ('static int sm64_preparing;\nstatic void gpu_prepare_flush(int);\n'
                   'static void gpu_prepare_begin(void);\nstatic void gpu_acquire_pending(void);\n'
                   'static void gpu_prepare_texture(unsigned);\n'
                   'static void gpu_prepare_publish(unsigned *, unsigned);\n'
                   'extern unsigned sm64_prepare_capacity_flushes;\n')
    gpu = prefix + gpu
    if prep:
        a = gpu.index('    if (g_flip_pending) {', gpu.index('static void gpu_start_frame(void) {'))
        b = gpu.index('    g_st_cache_valid = 0;', a)
        gpu = gpu[:a] + '''    if (g_tex_epoch == UINT32_MAX) {
        gpu_acquire_pending();
        for (uint32_t i = 0; i < MAX_TEX; i++)
            g_tex[i].slot_epoch[0] = g_tex[i].slot_epoch[1] = 0;
        g_tex_epoch = 0;
    }
    ++g_tex_epoch;
    gpu_prepare_begin();
''' + gpu[b:]
        gpu = replace(gpu, '    PROF_FLIP_BEGIN();', '    gpu_prepare_flush(1);\n    PROF_FLIP_BEGIN();')
        gpu = replace(gpu, '    uint8_t slotc = t->cur ^ 1u;',
                      '    uint8_t slotc = t->cur ^ 1u;\n    gpu_prepare_texture(t->slot_epoch[slotc]);')
        gpu = replace(gpu, 'Earlier frames have retired: gpu_start_frame waits for their flip.',
                      'Prior-frame reuse is fenced by gpu_prepare_texture above.')
        gpu = replace(gpu, '        of_gpu_finish();', '        gpu_prepare_flush(1);\n        of_gpu_finish();')
        gpu = replace(gpu, '    if (g_has_gpu) of_gpu_shutdown();',
                      '    gpu_prepare_flush(1);\n    if (g_has_gpu) of_gpu_shutdown();')
        # IDs are minted modulo MAX_TEX, but g_tex_count itself is unbounded.
        gpu = gpu.replace('i < g_tex_count;', 'i < g_tex_count && i < MAX_TEX;')
        gpu += '\n' + (HERE/'prepare.inc').read_text()
    if audio:
        gpu = replace(gpu, '    while (!of_gpu_fence_reached(token)) {',
                      '    while (!of_gpu_fence_reached(token)) {\n        sm64_audio_service();')
        gpu = replace(gpu, '    for (size_t tri = 0; tri < buf_vbo_num_tris; tri++) {',
                      '    for (size_t tri = 0; tri < buf_vbo_num_tris; tri++) {\n'
                      '        if ((tri & 15u) == 0) sm64_audio_service();')
        for loop in ('for (; i + 1 < n; i += 2) {', 'for (; i + 3 < n; i += 4) {'):
            assert loop in gpu
            gpu = gpu.replace(loop, loop+'\n            if ((i & 255u) == 0) sm64_audio_service();')
        pc = prefix.split('#define')[0] + pc
        pc = replace(pc, 'static void gfx_run_dl(Gfx* cmd) {\n    for (;;) {',
                     'static void gfx_run_dl(Gfx* cmd) {\n    unsigned service_commands = 0;\n    for (;;) {\n'
                     '        if ((service_commands++ & 31u) == 0) sm64_audio_service();')
        wm = 'extern void sm64_audio_service(void);\n' + wm
        wm = replace(wm, '    unsigned now = of_time_us();',
                     '    sm64_audio_service();\n    unsigned now = of_time_us();')
    sources = {'gfx_gpu.c':gpu, 'gfx_pc.c':pc, 'wm_pocket.c':wm}
    sources['audio_service.c'] = ((HERE/'audio_service.c').read_text() if audio
                                  else 'void sm64_audio_service(void) {}\n')
    exports = ['gfx_gpu_boot','gfx_gpu_present','gfx_gpu_vtx_cache_begin','gfx_gpu_vtx_cache_tri',
               'gpu_present_prof_get','gpu_ring_prof_get','gpu_vc_prof_get','gfx_get_dimensions',
               'gfx_init','gfx_shutdown','gfx_get_current_rendering_api','gfx_start_frame','gfx_run','gfx_end_frame']
    if audio: exports += ['produce_one_frame']
    overlay.build(label, sources, {x:x for x in exports if x in overlay.orig},
                  ['gfx_gpu_api','gfx_pocket_wm_api'], bind=('gfx_vc_true','gfx_current_dimensions'))
    dest = OUT/'overlays'/label
    (dest/'of_gpu.h').write_text(header)
    syms = overlay.symbols(dest/'overlay.elf')
    probes = {k:v['addr'] for k,v in syms.items() if k.startswith('sm64_prepare_') or k=='sm64_audio_deadlines'}
    (dest/'probes.json').write_text(json.dumps(probes, indent=2)+'\n')
    (dest/'white-address.txt').write_text(hex(syms['g_white_tex']['addr'])+'\n')
    patch = ''
    for n,p in paths.items():
        name = str(p.relative_to(SM.parent.parent))
        patch += ''.join(difflib.unified_diff(old[n].splitlines(True), sources[n].splitlines(True),
                                             fromfile='a/'+name, tofile='b/'+name))
    (dest/'renderer.patch').write_text(patch)

if __name__ == '__main__': main(sys.argv[1])
