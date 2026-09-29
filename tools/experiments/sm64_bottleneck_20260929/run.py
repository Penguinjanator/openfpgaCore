#!/usr/bin/env python3
"""Run one scene of the real SM64 binary (no overlay) on a build.py model.

    run.py <label> <scene> <start> <count> [--cpu-period N] [--elf PATH]

scene is intro or attract, as in sm64_coupled_20260922 (castle: intro 1040 64;
castle + CPU traffic: intro 1040 32 --cpu-period 64; Bowser: attract 1140 32;
title head: attract 360 32).  Output: build/sm64-bottleneck-20260929/<label>/runs/.
"""
import argparse, os, subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT/'build/sm64-bottleneck-20260929'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('label'); p.add_argument('scene', choices=['intro', 'attract'])
    p.add_argument('start', type=int); p.add_argument('count', type=int)
    p.add_argument('--cpu-period', type=int, default=0)
    p.add_argument('--elf', type=Path, default=ROOT.parent/'SM64/.obj/sm64/app.elf')
    p.add_argument('--dcache-kib', type=int, help='CPU D$ size in the qsim model (os30: 128)')
    a = p.parse_args()
    model = OUT/a.label
    d = model/'runs'/(f'{a.scene}-{a.start}-{a.count}-cpu{a.cpu_period}'
                      + (f'-d{a.dcache_kib}' if a.dcache_kib else ''))
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob('frame-tick-*.bin'): old.unlink()
    with a.elf.open('rb') as f:
        syms = {s.name: s['st_value'] for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols()}
    env = {k: v for k, v in os.environ.items() if not k.startswith(('QSIM_', 'COUPLED_'))}
    env.update(QSIM_SM64='1', QSIM_WHITE_ADDRESS=hex(syms['g_white_tex']),
               COUPLED_START_FRAME=str(a.start), COUPLED_CPU_PERIOD=str(a.cpu_period),
               COUPLED_AUDIO_PERIOD='0', COUPLED_RENDER_PC=hex(syms['gpu_start_frame']),
               COUPLED_SOUND='1')
    if a.scene == 'intro': env['QSIM_SM64_INTRO'] = '1'
    if a.dcache_kib: env['QSIM_DCACHE_KIB'] = str(a.dcache_kib)
    cmd = [str(model/'obj/Vtb_gpu_transluc'), str(a.elf.resolve()),
           '--app', str(ROOT/'build/sm64-estimates-20260922/sm64.app'), '--out', str(d),
           '--frames', str(a.start + a.count), '--profile', '--gpu-sched', 'eager',
           '--max-insns', '12000000000']
    with (d/'run.log').open('w') as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=3600)
    print(d)

if __name__ == '__main__': main()
