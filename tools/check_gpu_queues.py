#!/usr/bin/env python3
"""Compare the GPU texture queues and write combiner against the serial path.

Framebuffer bytes and consumed perspective arithmetic must match. Speculative
reciprocal lookups can differ when a faster pipeline retires a short span sooner.
Cycle totals describe the GPU test component, not complete-game performance.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from check_gpu_recip_cache import ROOT, FLAGS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--profile', choices=('pocket', 'mister'), default='pocket')
    ap.add_argument('--reset-only', action='store_true')
    ap.add_argument('--write-pipeline', type=int, choices=(0, 1),
                    help='Override the target combiner pipeline setting')
    args = ap.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    common = ROOT/'src/fpga/common'; test = ROOT/'src/fpga/test'
    sources = [test/'tb_gpu.v', common/'gpu_core.v', common/'gpu_edge_walker.v',
               common/'gpu_tex_cache.v', ROOT/'tools/tests/gpu_recip_cache.cpp']
    reset_source = ROOT/'tools/tests/gpu_queue_reset.cpp'
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [*sources, reset_source, test/'tb_gpu_acceptance_main.cpp']}
    modes = {'serial': (0, 0), 'stream': (1, 0), 'combined': (1, 1)}
    flags = list(FLAGS)
    pipeline = args.write_pipeline if args.write_pipeline is not None else 0
    flags += ['-GGPU_WRITE_COMBINE_PIPE='+str(pipeline)]
    if args.profile == 'mister':
        enabled = ('INCLUDE_PARAM_TRI', 'INCLUDE_VERT_TRI', 'INCLUDE_PARAM_TRI_RECS',
                   'GPU_EW_PARALLEL_DIVS', 'INCLUDE_CLIP_TRI', 'INCLUDE_GPU_XFORM_MAC', 'INCLUDE_COMBINE')
        replacements = {'-G'+key+'=0': '-G'+key+'=1' for key in enabled}
        flags = [replacements.get(flag, flag) for flag in flags]
        flags = ['-GGPU_Z_READ_WINDOW=4' if f == '-GGPU_Z_READ_WINDOW=1' else f for f in flags]
        flags += ['-GGPU_TEX_CACHE_SET_BITS=11', '+define+INCLUDE_EARLY_Z_CAPTURE']

    def build(name):
        stream, combine = (1, 1) if name == 'reset' else modes[name]
        build_sources = [*sources[:-1], reset_source] if name == 'reset' else sources
        cmd = ['verilator', '--cc', '--exe', '--build', '--trace', '-j', str(args.jobs),
               '-Wall', '-Wno-fatal', '-Wno-BADVLTPRAGMA', '--top-module', 'tb_gpu',
               '--Mdir', str(out/name), '-I'+str(common), '-CFLAGS', '-std=c++17 -O2 -I'+str(test),
               '-GGPU_STREAM_PIPE='+str(stream), '-GGPU_WRITE_COMBINE='+str(combine),
               *flags, *map(str, build_sources)]
        with (out/f'build-{name}.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        return out/name/'Vtb_gpu'

    names = ['reset'] if args.reset_only else [*modes, 'reset']
    with ThreadPoolExecutor(max_workers=2) as pool:
        binaries = dict(zip(names, pool.map(build, names)))
    reset_binary = binaries.pop('reset')
    results = {}
    for label, plusargs in [('quiet', []), ('delayed', ['+gpu_rd_latency=24',
                            '+gpu_rd_latency_var=1', '+gpu_wr_latency=17'])]:
        reset_run = subprocess.run([str(reset_binary), *plusargs], capture_output=True, text=True)
        (out/f'{label}-reset.log').write_text(reset_run.stdout+reset_run.stderr)
        reset_run.check_returncode()
        print(label, reset_run.stdout.splitlines()[-1], flush=True)
        results[label] = runs = {}
        if args.reset_only:
            continue
        for mode, binary in binaries.items():
            run = subprocess.run([str(binary), *plusargs], capture_output=True, text=True)
            (out/f'{label}-{mode}.log').write_text(run.stdout+run.stderr)
            run.check_returncode()
            rows = {}
            for line in run.stdout.splitlines():
                if line.startswith('RESULT '):
                    _, kind, number, cycles, pixels, requests, hits, arithmetic, changed = line.split()
                    rows[f'{kind}-{number}'] = dict(cycles=int(cycles), pixels=pixels,
                        requests=int(requests), hits=int(hits), arithmetic=arithmetic, changed=int(changed))
            assert len(rows) == 394, (mode, len(rows))
            runs[mode] = rows
        for mode in ('stream', 'combined'):
            for key, before in runs['serial'].items():
                after = runs[mode][key]
                for field in ('pixels', 'arithmetic', 'changed'):
                    assert before[field] == after[field], (label, mode, key, field, before, after)
            totals = [sum(row['cycles'] for row in runs[m].values()) for m in ('serial', mode)]
            print(label, mode, *totals, f'{100*(totals[0]-totals[1])/totals[0]:.2f}% fewer cycles', flush=True)
    (out/'results.json').write_text(json.dumps(dict(sources=manifest, profile=args.profile, flags=flags,
        modes=modes, results=results), indent=2)+'\n')
    print('PASS: reset recovery' if args.reset_only else
          'PASS: 788 cases per mode and 256 resets; framebuffer and consumed arithmetic match')


if __name__ == '__main__':
    main()
