#!/usr/bin/env python3
"""Measure CPU throughput using a verified Pocket CPU/GPU transport simulator.

Cycles per operation include address/loop overhead; they are not instruction
latencies. Scanout competes for memory; simultaneous GPU/audio load is absent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['fsgnj', 'fadd', 'fmul', 'fmadd', 'fdiv', 'fsqrt',
         'uncached_store32', 'uncached_store16', 'uncached_store8',
         'uncached_load32', 'ring_append32', 'taken_branch_loop']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--transport', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.transport / 'results.json').read_text())
    simulator = Path(manifest['simulator'])
    if hashlib.sha256(simulator.read_bytes()).hexdigest() != manifest['simulator_sha256']:
        raise RuntimeError('Simulator does not match its RTL manifest')
    with (out / 'generate.log').open('w') as log:
        subprocess.run(['python3', str(ROOT / 'src/fpga/test/cpu_stress/generate.py'),
                        str(out)], stdout=log, stderr=subprocess.STDOUT, check=True)
    for name in ('start.S', 'link.ld'):
        shutil.copy2(ROOT / 'src/fpga/test/cpu_stress' / name, out)
    program = ROOT / 'tools/tests/pocket_cpu_latency.c'
    shutil.copy2(program, out / 'main.c')
    container = ['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
                 '-v', f'{out}:{out}', '-w', str(out), 'openfpgaos-firmware']
    commands = [container + ['riscv64-unknown-elf-gcc', '-march=rv32imafc_zicsr_zifencei',
        '-mabi=ilp32f', '-O2', '-ffreestanding', '-fno-builtin', '-nostdlib',
        '-nostartfiles', '-Wl,-T,link.ld', '-Wl,--no-relax', 'start.S', 'main.c', '-o', 'latency.elf'],
        container + ['riscv64-unknown-elf-objcopy', '-O', 'binary', 'latency.elf', 'latency.bin']]
    with (out / 'build.log').open('w') as log:
        for command in commands:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    report = dict(scope=__doc__, rtl=manifest['rtl'],
                  program_sha256=hashlib.sha256(program.read_bytes()).hexdigest(), runs={})
    for mode, scan in [('quiet', '0'), ('scanout', '1')]:
        env = dict(os.environ, SCAN_ENABLE=scan, SCAN_PERIOD='8333', SCAN_LEN='80',
                   SCAN_ACTIVE='200', SCAN_TOTAL='200', SCAN_BASE_HW='0x1800000',
                   STRIKE_SCAN_PERIOD='1000000000')
        logpath = out / (mode + '.log')
        with logpath.open('w') as log:
            subprocess.run([str(simulator), 'latency.bin', '10000000'], cwd=out,
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        text = logpath.read_text()
        uart = text.split('=== UART BEGIN ===')[-1].split('=== UART END ===')[0]
        rows = [[int(v, 16) for v in line.split()] for line in
                re.findall(r'^LATENCY ([0-9a-f ]+)$', uart, re.M)]
        if len(rows) != 2 * len(NAMES) or 'LATENCY PASS HAL init' not in uart:
            raise RuntimeError('Missing latency results: ' + mode)
        if any(len(row) != 4 or row[0] != i % len(NAMES) or row[1] != 1024
               for i, row in enumerate(rows)):
            raise RuntimeError('Invalid latency results: ' + mode)
        if 'WCONF: mism=0 spurious=0 exp_fifo=0 aw_fifo=0 run_left=0' not in text:
            raise RuntimeError('Write-delivery oracle failed')
        result = {NAMES[kind]: dict(operations=n, cycles=cycles, cycles_per_op=cycles/n)
                  for kind, n, cycles, _ in rows[len(NAMES):]}
        report['runs'][mode] = result
        print(mode, json.dumps(result), flush=True)
    (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
