#!/usr/bin/env python3
"""Build and scoreboard the GPU render cache against an arbiter-like memory model.

Defaults to the production RTL (os30, INCLUDE_GPU_RENDER_CACHE); pass --rtl for
the experimental copies.  os30 geometry: --set-bits 6 --word-bits 4 --ways 2
--cache-all --addr-width 26 --poison-collisions.
"""
from pathlib import Path
import argparse
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'build/gpu-color-depth-cache')
    parser.add_argument('--set-bits', type=int, default=2)
    parser.add_argument('--word-bits', type=int, default=2)
    parser.add_argument('--ways', type=int, default=4)
    parser.add_argument('--cache-all', action='store_true')
    parser.add_argument('--addr-width', type=int, default=32)
    parser.add_argument('--seeds', type=int, default=3)
    parser.add_argument('--rtl', type=Path,
                        default=ROOT/'src/fpga/common/gpu_color_depth_cache.sv')
    parser.add_argument('--poison-collisions', action='store_true',
                        help='Inject hostile RAM read/write collision data in the BRAM implementation')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cmd = ['verilator', '--cc', '--exe', '--build', '-j', '3', '-Wno-fatal',
           '--top-module', 'gpu_color_depth_cache', '--Mdir', str(out/'obj'),
           f'-GSET_BITS={args.set_bits}', f'-GWORD_BITS={args.word_bits}',
           f'-GWAYS={args.ways}',
           f'-GADDR_W={args.addr_width}',
           '-CFLAGS', '-std=c++17 -O2',
           str(args.rtl.resolve()),
           str(ROOT/'tools/tests/gpu_color_depth_cache.cpp')]
    cmd[cmd.index('-CFLAGS')+1] += (f' -DSET_BITS_MODEL={args.set_bits} -DWORD_BITS_MODEL={args.word_bits}'
                                     f' -DWAYS_MODEL={args.ways} -DCACHE_ALL_MODEL={int(args.cache_all)}')
    if 'bus_reset_n' in args.rtl.read_text():
        cmd[cmd.index('-CFLAGS')+1] += ' -DHAS_BUS_RESET'
    if args.poison_collisions:
        cmd.append('+define+CACHE_POISON_COLLISIONS')
    if args.cache_all:
        cmd.append('-GCACHE_ALL=1')
    with (out/'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    for seed in range(1, args.seeds+1):
        subprocess.run([str(out/'obj/Vgpu_color_depth_cache'), str(seed)], check=True)

if __name__ == '__main__':
    main()
