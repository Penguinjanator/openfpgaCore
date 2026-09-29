#!/usr/bin/env python3
"""Compare cache alias/eviction traffic on two Pocket CPU system simulators.

First build each simulator with check_pocket_gpu_transport.py --cpu <netlist>.
The workloads check loads, dirty evictions, AMOs and uncached flush visibility.
Their timing is a cache stress measurement, not game FPS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(command, log, **kwargs):
    with log.open('w') as f:
        subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True, **kwargs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--before', type=Path, required=True, help='Transport output directory')
    ap.add_argument('--after', type=Path, required=True, help='Transport output directory')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = ROOT / 'src/fpga/test/cpu_stress'
    run(['python3', str(original / 'generate.py'), str(out)], out / 'generate.log')
    for name in ('start.S', 'link.ld'):
        (out / name).write_bytes((original / name).read_bytes())
    program = ROOT / 'tools/tests/pocket_cache_hazards.c'
    (out / 'main.c').write_bytes(program.read_bytes())
    container = ['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
                 '-v', f'{out}:{out}', '-w', str(out), 'openfpgaos-firmware']
    run([*container, 'riscv64-unknown-elf-gcc', '-march=rv32imafc_zicsr_zifencei',
         '-mabi=ilp32f', '-O2', '-ffreestanding', '-fno-builtin', '-nostdlib',
         '-nostartfiles', '-Wl,-T,link.ld', '-Wl,--no-relax', 'start.S', 'main.c',
         '-o', 'cache.elf'], out / 'firmware-build.log')
    run([*container, 'riscv64-unknown-elf-objcopy', '-O', 'binary', 'cache.elf', 'cache.bin'],
        out / 'objcopy.log')
    results = dict(program_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),
                   firmware_sha256=hashlib.sha256((out / 'cache.bin').read_bytes()).hexdigest(),
                   builds={}, runs={})
    for label in ('before', 'after'):
        manifest = json.loads((getattr(args, label) / 'results.json').read_text())
        simulator = Path(manifest['simulator'])
        if hashlib.sha256(simulator.read_bytes()).hexdigest() != manifest['simulator_sha256']:
            raise RuntimeError('Simulator no longer matches its source manifest')
        results['builds'][label] = dict(simulator=str(simulator), rtl=manifest['rtl'])
        for mode, enable in [('quiet', '0'), ('scanout', '1')]:
            env = dict(os.environ, SCAN_ENABLE=enable, SCAN_PERIOD='8333', SCAN_LEN='80',
                       SCAN_ACTIVE='200', SCAN_TOTAL='200', SCAN_BASE_HW='0x1800000',
                       STRIKE_SCAN_PERIOD='1000000000')
            log = out / (label + '-' + mode + '.log')
            run([str(simulator), 'cache.bin', '40000000'], log, cwd=out, env=env)
            text = log.read_text()
            uart = text.split('=== UART BEGIN ===')[-1].split('=== UART END ===')[0]
            rows = [[int(x, 16) for x in line.split()]
                    for line in re.findall(r'^CACHE ([0-9a-f ]+)$', uart, re.M)]
            if len(rows) != 3 or 'CACHE PASS HAL init' not in uart:
                raise RuntimeError('Cache checks failed: ' + str(log))
            if 'WCONF: mism=0 spurious=0 exp_fifo=0 aw_fifo=0 run_left=0' not in text:
                raise RuntimeError('Write delivery failed: ' + str(log))
            results['runs'][label + '-' + mode] = rows
            print(label, mode, rows, flush=True)
    for mode in ('quiet', 'scanout'):
        before, after = (results['runs'][label + '-' + mode] for label in ('before', 'after'))
        if any(a[0] != b[0] or a[2] != b[2] for a, b in zip(before, after)):
            raise RuntimeError('Workload or output hashes differ')
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
