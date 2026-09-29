#!/usr/bin/env python3
"""Pocket write-burst / depth-combine variants of the live SM64 model."""
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'tools/experiments/sm64_coupled_20260922'
OUT = ROOT/'build/sm64-wburst-20260923'
BURSTS = ['-GGPU_WRITE_COMBINE_FAST_FLUSH=1', '-GGPU_WRITE_GATHER=1',
          '-GGPU_MASKED_WRITE_BURSTS=1']
VARIANTS = {
    'baseline': [],
    # INCLUDE_GPU_WRITE_BURSTS as os25 ships it.
    'bursts': BURSTS,
    # Plus depth-tested combining and the burst-preserving index (MiSTer set).
    'burstsz': BURSTS + ['-GGPU_WRITE_COMBINE_Z=1', '-GGPU_WRITE_COMBINE_BURST_HASH=1'],
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('variant', choices=list(VARIANTS))
    a = p.parse_args()
    out = OUT/a.variant
    out.mkdir(parents=True, exist_ok=True)
    source = (BASE/'build.py').read_text()
    old = "OUT = ROOT/'build/sm64-coupled-20260922'"
    assert source.count(old) == 1
    source = source.replace(old, 'OUT = PRIVATE_OUT')
    old = "'--top-module','tb_gpu_transluc',"
    assert source.count(old) == 1
    source = source.replace(old, old + '*PARAMS,')
    ns = dict(__file__=str(BASE/'build.py'), __name__='private_build',
              PRIVATE_OUT=out, PARAMS=VARIANTS[a.variant])
    exec(compile(source, str(BASE/'build.py'), 'exec'), ns)
    ns['main']()

if __name__ == '__main__': main()
