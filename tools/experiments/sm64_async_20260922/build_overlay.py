#!/usr/bin/env python3
"""Private full-list and chunk-list SM64 overlays, with retained audio changes."""
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'build/sm64-async-20260922'
BASE=ROOT/'build/sm64-schedule-20260922'

def replace(s,a,b):
    assert s.count(a)==1,(a[:90],s.count(a))
    return s.replace(a,b,1)

def main(label):
    assert label in ['async','chunk','early','async_audio','chunk_audio','early_audio']
    audio=label.endswith('_audio')
    words=8192 if label.startswith('chunk') else 32768
    source=BASE/'overlays'/('audio' if audio else 'control')
    OUT.mkdir(parents=True,exist_ok=True)
    inc=OUT/'include';inc.mkdir(exist_ok=True)
    helper=(ROOT/'tools/experiments/sm64_renderer_20260922/build_overlay.py').read_text()
    helper=helper.replace("'-I'+str(sdk/'include')","'-I'+str(out/'include'),'-I'+str(sdk/'include')")
    (OUT/'overlay_helper.py').write_text(helper)
    spec=importlib.util.spec_from_file_location('async_overlay',OUT/'overlay_helper.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    header=(source/'of_gpu.h').read_text()
    a=header.index('static inline void _gpu_flush_cmd_stream(void) {')
    b=header.index('static inline void _gpu_ring_ensure(',a)
    header=header[:a]+'static inline void _gpu_flush_cmd_stream(void) { list_flush(0); }\n\n'+header[b:]
    a=header.index('static inline void _gpu_stream_reserve_words(uint32_t words) {')
    b=header.index('/* Append one word',a)
    header=header[:a]+'''static inline void _gpu_stream_reserve_words(uint32_t words) {
    if (words>SM64_LIST_WORDS || !_gpu_batch_buf) __builtin_trap();
    if (words>SM64_LIST_WORDS-_gpu_cmd_words) {
        sm64_list_capacity_flushes++;
        list_flush(1);
    }
}

'''+header[b:]
    header=replace(header,'_gpu_cmd_words >= OF_GPU_COMMAND_STREAM_BATCH_WORDS',
                   '_gpu_cmd_words >= SM64_LIST_WORDS')
    (inc/'of_gpu.h').write_text(header)
    (inc/'audio_clock.h').write_text((BASE/'include/audio_clock.h').read_text())
    gpu=(source/'gfx_gpu.c').read_text()
    prefix=f'''#define SM64_LIST_WORDS {words}u
static void list_flush(int);
static void list_begin(void);
static void list_acquire(void);
static void list_texture(unsigned);
extern unsigned sm64_list_capacity_flushes;
'''
    if label.startswith('early'):prefix='#define SM64_LIST_EARLY_CLEAR 1\n'+prefix
    gpu=prefix+gpu
    a=gpu.index('    if (g_flip_pending) {',gpu.index('static void gpu_start_frame(void) {'))
    b=gpu.index('    g_st_cache_valid = 0;',a)
    gpu=gpu[:a]+'    list_begin();\n'+gpu[b:]
    gpu=replace(gpu,'    PROF_FLIP_BEGIN();','    list_acquire();\n    PROF_FLIP_BEGIN();')
    if label.startswith('early'):
        gpu=replace(gpu,'''    /* Let the GPU clear both surfaces while the CPU processes vertices. */
    of_gpu_kick_now();''', '''    /* Start clears early when the preceding frame is already retired.
     * Otherwise retain the full-list overlap with that frame. */
    if (!g_flip_pending) list_flush(1);''')
    gpu=replace(gpu,'    uint8_t slotc = t->cur ^ 1u;',
                '    uint8_t slotc = t->cur ^ 1u;\n    list_texture(t->slot_epoch[slotc]);')
    gpu=gpu.replace('i < g_tex_count;', 'i < g_tex_count && i < MAX_TEX;')
    gpu=replace(gpu,'    if (g_has_gpu) of_gpu_shutdown();',
                '    list_flush(1);\n    if (g_has_gpu) of_gpu_shutdown();')
    gpu+='\n'+(HERE/'list.inc').read_text()
    sources={n:(source/n).read_text() for n in ['gfx_pc.c','wm_pocket.c','audio_service.c']}
    sources['gfx_gpu.c']=gpu
    manifest=json.loads((source/'manifest.json').read_text())
    module.build(label,sources,manifest['forward'],manifest['data_forward'],
                 bind=('gfx_vc_true','gfx_current_dimensions'))
    dest=OUT/'overlays'/label
    (dest/'of_gpu.h').write_text(header)
    syms=module.symbols(dest/'overlay.elf')
    probes={k:v['addr'] for k,v in syms.items() if k.startswith('sm64_list_') or k=='sm64_audio_deadlines'}
    (dest/'probes.json').write_text(json.dumps(probes,indent=2)+'\n')

if __name__=='__main__':main(sys.argv[1])
