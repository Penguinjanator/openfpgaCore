#!/usr/bin/env python3
"""Check production SDK GPU initialization with modeled MMIO and sanitizers."""
import argparse
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--gpu-header', type=Path, default=root / 'src/firmware/api/of_gpu.h')
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    header = args.gpu_header.read_text()
    old = '#define OF_GPU_REG(off)         (*(volatile uint32_t *)(_gpu_base + (off)))'
    if header.count(old) != 1:
        raise RuntimeError('MMIO definition changed')
    (out / 'of_gpu_test.h').write_text(header.replace(old, '#define OF_GPU_REG(off) (*reg(off))'))
    with (out / 'build.log').open('w') as log:
        subprocess.run(['cc', '-std=gnu11', '-O2', '-g', '-no-pie',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                        '-I' + str(out), '-I' + str(root / 'src/firmware/api'),
                        str(root / 'tools/tests/gpu_init.c'), '-o', str(out / 'test')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    run = subprocess.run([str(out / 'test')], capture_output=True, text=True, check=True)
    (out / 'run.log').write_text(run.stdout + run.stderr)
    print(run.stdout, end='')


if __name__ == '__main__':
    main()
