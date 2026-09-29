#!/usr/bin/env python3
"""Replay qsim captures against freshly compiled baseline and candidate GPU RTL.

Requires an os25 manifest from check_gpu_target_matrix.py and an SDK qsim tree.
Compares the displayed framebuffer, fence and full SDRAM digest to the C oracle.
Reported cycles cover serialized GPU batches, not complete application frames.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log):
    with log.open('w') as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=600)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--qsim', type=Path, required=True)
    ap.add_argument('--gpu-config', type=Path, required=True)
    ap.add_argument('--capture', type=Path, action='append', required=True)
    ap.add_argument('--candidate-macro', action='append', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=2)
    args = ap.parse_args()
    if args.jobs < 1 or any(not re.fullmatch(r'[A-Z_][A-Z_0-9]*', m)
                           for m in args.candidate_macro):
        ap.error('Invalid jobs or candidate macro')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.gpu_config.read_text())
    if config['variant']['variant'] != 'os25':
        ap.error('The qsim raster oracle currently describes os25')
    baseline_macros = config['variant']['defs'].split()
    if set(baseline_macros) & set(args.candidate_macro):
        ap.error('Candidate macro already enabled in baseline')
    frozen = out / 'frozen'
    shutil.copytree(ROOT / 'src/fpga/common', frozen / 'common')
    test = ROOT / 'src/fpga/test'
    top = (test / 'tb_gpu.v').read_text()
    # qsim snapshots use the entire physical SDRAM address range. Only the
    # simulation memory is enlarged; GPU addressing/arithmetic stays intact.
    top = top.replace('[0:1048575]', '[0:16777215]')
    top = top.replace('[19:0]', '[23:0]')
    top = re.sub(r'(reg \[31:0\] (?:sdram_mem|sram_mem) \[[^;]+);',
                 r'\1 /* verilator public_flat_rw */;', top)
    (frozen / 'tb_gpu.v').write_text(top)
    shutil.copy2(ROOT / 'tools/tests/gpu_qsim_replay.cpp', frozen)
    qsim = args.qsim.resolve()
    shutil.copy2(qsim / 'gpuvec.h', frozen)
    run(['make', '-s', '-C', str(qsim), 'gputest'], out / 'model-build.log')
    report = dict(config=config, candidate_macros=args.candidate_macro,
                  model_sha256=digest(qsim / 'gputest'),
                  sources={str(p.relative_to(frozen)): digest(p)
                           for p in sorted(frozen.rglob('*')) if p.is_file()}, runs=[])

    def build(label):
        macros = baseline_macros + (args.candidate_macro if label == 'candidate' else [])
        dest = out / label
        command = ['verilator', '--cc', '--exe', '--build', '-j', str(args.jobs),
                   '-Wno-fatal', '-Wno-BADVLTPRAGMA', '--top-module', 'tb_gpu',
                   '--Mdir', str(dest), '-I' + str(frozen / 'common'),
                   '-CFLAGS', '-std=c++17 -O2 -I' + str(frozen),
                   *['+define+' + m for m in macros], *config['flags'],
                   str(frozen / 'tb_gpu.v'),
                   *[str(frozen / 'common' / n) for n in
                     ('gpu_core.v', 'gpu_edge_walker.v', 'gpu_tex_cache.v')],
                   str(frozen / 'gpu_qsim_replay.cpp')]
        run(command, out / (label + '-build.log'))
        return dest / 'Vtb_gpu'

    with ThreadPoolExecutor(max_workers=2) as pool:
        binaries = dict(zip(('baseline', 'candidate'), pool.map(build, ('baseline', 'candidate'))))
    report['binaries'] = {label: digest(binary) for label, binary in binaries.items()}
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    for capture in args.capture:
        capture = capture.resolve()
        frames = {int(row['frame']): row for row in
                  csv.DictReader((capture / 'frames.csv').open())}
        vectors = sorted((capture / 'gpuvec').glob('frame_*.vec'))
        if not vectors:
            raise RuntimeError('No captured frames: ' + str(capture))
        for vec in vectors:
            dest = out / (capture.name + '-' + vec.stem)
            dest.mkdir()
            oracle = dest / 'model.bin'
            run([str(qsim / 'gputest'), 'run', str(vec), str(oracle)], dest / 'model.log')
            data = oracle.read_bytes()
            h = 0xcbf29ce484222325
            for b in data[:-12]:
                h = ((h ^ b) * 0x100000001b3) & 0xffffffffffffffff
            frame = int(vec.stem.removeprefix('frame_'))
            if f'{h:016x}' != frames[frame]['hash_px']:
                raise RuntimeError('Incomplete capture: ' + str(vec))
            for condition, plus in [('quiet', []), ('delayed', ['+gpu_rd_latency=24',
                                     '+gpu_rd_latency_var=1', '+gpu_wr_latency=17'])]:
                row = dict(capture=str(vec), vector_sha256=digest(vec),
                           condition=condition, oracle_sha256=digest(oracle), timings={})
                for label, binary in binaries.items():
                    output = dest / (label + '-' + condition + '.bin')
                    log = output.with_suffix('.log')
                    run([str(binary), str(vec), str(output), *plus], log)
                    if output.read_bytes() != data:
                        raise RuntimeError('RTL/C oracle mismatch: ' + str(output))
                    match = re.search(r'RESULT cycles=(\d+) busy_cycles=(\d+) batches=(\d+)', log.read_text())
                    if not match:
                        raise RuntimeError('Missing nonvacuous timing: ' + str(log))
                    row['timings'][label] = dict(zip(('cycles', 'busy_cycles', 'batches'), map(int, match.groups())))
                    if not row['timings'][label]['batches']:
                        raise RuntimeError('Empty GPU workload')
                report['runs'].append(row)
            (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
            print('PASS', capture.name, vec.stem, 'baseline/candidate, quiet/delayed, full oracle', flush=True)
    print('PASS:', len(report['runs']), 'GPU replay comparisons', flush=True)


if __name__ == '__main__':
    main()
