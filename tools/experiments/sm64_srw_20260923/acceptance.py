#!/usr/bin/env python3
"""GPU acceptance + window-coherence oracle on the working-tree selective waits.

Slow posted writes (71 and 200 cycles) keep writes queued/in flight while the
next z/colour line fill is requested -- the case the selective barrier relaxes.
"""
import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT/'build/sm64-srw-20260923/acceptance'
WINDOWS = HERE.parent/'sm64_windows_20260923'
CONFIGS = {
    'srw10_w4': (['INCLUDE_GPU_SELECTIVE_READ_WAIT'], []),
    'srw6_z8': (['INCLUDE_GPU_SELECTIVE_READ_WAIT'], ['-GGPU_Z_READ_WINDOW=8']),
    # os30 with the render cache (write combiner off, texture queues in MLAB).
    'os30_cache': (['INCLUDE_GPU_SELECTIVE_READ_WAIT', 'INCLUDE_GPU_RENDER_CACHE'],
                   ['-GGPU_Z_READ_WINDOW=8', '-GGPU_WRITE_COMBINE=0']),
    # os30 as shipped from 2026-09-25: render cache without the selective waits.
    'os30_cache_nosrw': (['INCLUDE_GPU_RENDER_CACHE'], ['-GGPU_Z_READ_WINDOW=8', '-GGPU_WRITE_COMBINE=0']),
    'srw10_w16': (['INCLUDE_GPU_SELECTIVE_READ_WAIT'], ['-GGPU_Z_READ_WINDOW=16', '-GGPU_CB_READ_WINDOW=4']),
    'srw20_w16': (['INCLUDE_GPU_SELECTIVE_READ_WAIT', 'GPU_SRW_TAG_W=20'],
                  ['-GGPU_Z_READ_WINDOW=16', '-GGPU_CB_READ_WINDOW=4']),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config', choices=list(CONFIGS))
    a = ap.parse_args()
    defs, gparams = CONFIGS[a.config]
    out = OUT/a.config
    out.mkdir(parents=True, exist_ok=True)
    common = ROOT/'src/fpga/common'
    top = out/'tb_gpu.v'
    shutil.copy2(ROOT/'src/fpga/test/tb_gpu.v', top)
    source = (ROOT/'src/fpga/test/tb_gpu_acceptance_main.cpp').read_text()
    source = source.replace('int timeout = 400000', 'int timeout = 4000000')
    source = source.replace('int main(int argc, char **argv) {',
        (WINDOWS/'coherence.inc').read_text()+'\nint main(int argc, char **argv) {')
    source = source.replace('    // ---- Standalone tests ----',
        '    test_private_window_coherence();\n    // ---- Standalone tests ----')
    cpp = out/'acceptance.cpp'
    cpp.write_text(source)
    cfg = json.loads((ROOT/'build/sm64-estimates-20260922/memory/config.json').read_text())['gpu']
    params = set(re.findall(r'parameter\s+(\w+)\s*=', top.read_text()))
    flags = [f'-G{k}={v}' for k, v in cfg['parameters'].items() if k in params]
    over = {g.split('=')[0] for g in gparams}
    flags = [f for f in flags if f.split('=')[0] not in over] + gparams
    cfgdefs = cfg['variant']['defs'].split()
    if 'INCLUDE_GPU_RENDER_CACHE' in defs:
        cfgdefs = cfgdefs + ['INCLUDE_TEX_QUEUE_MLAB']
    cflags = '-std=c++17 -O2 -I'+str(ROOT/'src/fpga/test')+' ' + ' '.join('-D'+x for x in [
        'GPU_TEST_OS30_LEAN', 'GPU_TEST_TRUECOLOR', 'GPU_TEST_NO_PALETTE',
        'GPU_TEST_NO_PARAM_TRI', 'GPU_TEST_NO_PARAM_SPAN_Q29', 'GPU_TEST_XFORM',
        'GPU_TEST_NO_CLIP_TRI', 'GPU_TEST_NO_COMMAND_DMA'])
    cmd = ['verilator', '--cc', '--exe', '--build', '--trace', '-j', '3', '-Wno-fatal',
           '-Wno-BADVLTPRAGMA', '--top-module', 'tb_gpu', '--Mdir', str(out/'obj'),
           '-I'+str(common), '-CFLAGS', cflags, *flags,
           *['+define+'+d for d in cfgdefs + defs], str(top),
           *[str(common/f) for f in ['gpu_core.v', 'gpu_edge_walker.v', 'gpu_tex_cache.v',
                                     'gpu_color_depth_cache.sv']], str(cpp)]
    (out/'build-command.json').write_text(json.dumps(cmd, indent=2)+'\n')
    with (out/'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    ok = True
    for cond, args in [('normal', []),
                       ('slow71', ['+gpu_rd_latency=24', '+gpu_rd_latency_var=1', '+gpu_wr_latency=71']),
                       ('slow200', ['+gpu_rd_latency=24', '+gpu_rd_latency_var=1', '+gpu_wr_latency=200'])]:
        with (out/(cond+'.log')).open('w') as log:
            subprocess.run([str(out/'obj/Vtb_gpu'), *args], stdout=log, stderr=subprocess.STDOUT)
        text = (out/(cond+'.log')).read_text()
        m = re.search(r'Acceptance Results: (\d+) passed, (\d+) failed', text)
        print(a.config, cond, m[0] if m else 'NO RESULT', flush=True)
        ok = ok and bool(m) and int(m[2]) == 0
    raise SystemExit(0 if ok else 1)

if __name__ == '__main__': main()
