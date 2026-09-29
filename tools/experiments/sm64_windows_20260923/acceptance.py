#!/usr/bin/env python3
"""Run existing analytic GPU oracles with the private RTL and delayed memory."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from build import HERE, ROOT, OUT, VARIANTS

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('variant', choices=VARIANTS)
    ap.add_argument('--collect', action='store_true', help='Validate and fingerprint completed logs without rerunning')
    a = ap.parse_args()
    out = OUT/a.variant/'acceptance'
    out.mkdir(exist_ok=True)
    common = OUT/a.variant/'frozen/common'
    top = out/'tb_gpu.v'
    if not a.collect: shutil.copy2(ROOT/'src/fpga/test/tb_gpu.v', top)
    cpp = out/'acceptance.cpp'
    source = (ROOT/'src/fpga/test/tb_gpu_acceptance_main.cpp').read_text()
    # Artificial 71-cycle writes exceed three large tests' 400k-cycle default
    # timeout even on the unchanged baseline. Increase only the watchdog.
    source = source.replace('int timeout = 400000', 'int timeout = 2000000')
    source = source.replace('int main(int argc, char **argv) {',
        (HERE/'coherence.inc').read_text()+'\nint main(int argc, char **argv) {')
    source = source.replace('    // ---- Standalone tests ----',
        '    test_private_window_coherence();\n    // ---- Standalone tests ----')
    if not a.collect: cpp.write_text(source)
    cfg = json.loads((ROOT/'build/sm64-estimates-20260922/memory/config.json').read_text())['gpu']
    params = set(re.findall(r'parameter\s+(\w+)\s*=', top.read_text()))
    flags = [f'-G{k}={v}' for k,v in cfg['parameters'].items() if k in params]
    if a.variant.endswith('16') or a.variant == 'wide':
        flags = [f for f in flags if not f.startswith(('-GGPU_Z_READ_WINDOW=', '-GGPU_CB_READ_WINDOW='))]
        flags += ['-GGPU_Z_READ_WINDOW=16', '-GGPU_CB_READ_WINDOW=4']
    cflags = '-std=c++17 -O2 -I'+str(ROOT/'src/fpga/test')+' ' + ' '.join('-D'+x for x in [
        'GPU_TEST_OS30_LEAN', 'GPU_TEST_TRUECOLOR', 'GPU_TEST_NO_PALETTE',
        'GPU_TEST_NO_PARAM_TRI', 'GPU_TEST_NO_PARAM_SPAN_Q29', 'GPU_TEST_XFORM',
        'GPU_TEST_NO_CLIP_TRI', 'GPU_TEST_NO_COMMAND_DMA'])
    cmd = ['verilator','--cc','--exe','--build','--trace','-j','3','-Wno-fatal',
           '-Wno-BADVLTPRAGMA','--top-module','tb_gpu','--Mdir',str(out/'obj'),
           '-I'+str(common),'-CFLAGS',cflags, *flags,
           *['+define+'+d for d in cfg['variant']['defs'].split()], str(top),
           *[str(common/f) for f in ['gpu_core.v','gpu_edge_walker.v','gpu_tex_cache.v']], str(cpp)]
    if not a.collect:
        (out/'build-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
        with (out/'build.log').open('w') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    result = dict(variant=a.variant,conditions=[],inputs_sha256={
        str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            cpp,top,common/'gpu_core.v',common/'gpu_edge_walker.v',common/'gpu_tex_cache.v',
            ROOT/'src/fpga/test/doom_capture_replay.h',out/'obj/Vtb_gpu']})
    for condition, args in [('normal', []), ('delayed', ['+gpu_rd_latency=24',
            '+gpu_rd_latency_var=1', '+gpu_wr_latency=71'])]:
        if not a.collect:
            with (out/(condition+'.log')).open('w') as log:
                subprocess.run([str(out/'obj/Vtb_gpu'), *args],stdout=log,stderr=subprocess.STDOUT,check=True)
        logtext=(out/(condition+'.log')).read_text()
        match=re.search(r'Acceptance Results: (\d+) passed, (\d+) failed',logtext)
        assert match and int(match[2])==0,(a.variant,condition)
        result['conditions'].append(dict(name=condition,passed=int(match[1]),failed=int(match[2]),arguments=args))
        print(a.variant,condition,match[0],flush=True)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__ == '__main__': main()
