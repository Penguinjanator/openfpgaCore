#!/usr/bin/env python3
"""Working-tree GPU in the live SM64 model: read windows x selective waits."""
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'tools/experiments/sm64_coupled_20260922'
OUT = ROOT/'build/sm64-srw-20260923'
WIDE = ['-GGPU_Z_READ_WINDOW=16', '-GGPU_CB_READ_WINDOW=4']
SRW = ['+define+INCLUDE_GPU_SELECTIVE_READ_WAIT']
VARIANTS = {
    'base': [],
    'wide': WIDE,
    'srw': SRW,
    'wide_srw': WIDE + SRW,
    'wide_srw20': WIDE + SRW + ['+define+GPU_SRW_TAG_W=20'],
    'wide_srw6': WIDE + SRW + ['+define+GPU_SRW_TAG_W=6'],
    'srw6': SRW + ['+define+GPU_SRW_TAG_W=6'],
    'z16_srw6': ['-GGPU_Z_READ_WINDOW=16'] + SRW + ['+define+GPU_SRW_TAG_W=6'],
    'z8_srw6': ['-GGPU_Z_READ_WINDOW=8'] + SRW + ['+define+GPU_SRW_TAG_W=6'],
    # Same options; rebuilt after the registered-tag / departed-beat rewrite.
    'z8_srw6_v2': ['-GGPU_Z_READ_WINDOW=8'] + SRW + ['+define+GPU_SRW_TAG_W=6'],
    # Plus the texture-queue metadata FIFO (INCLUDE_TEX_QUEUE_RAM form).
    'z8_srw6_v3': ['-GGPU_Z_READ_WINDOW=8'] + SRW + ['+define+GPU_SRW_TAG_W=6'],
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('variant', choices=list(VARIANTS))
    a = p.parse_args()
    out = OUT/a.variant
    out.mkdir(parents=True, exist_ok=True)
    source = (BASE/'build.py').read_text()
    for old, new in [
        ("OUT = ROOT/'build/sm64-coupled-20260922'", 'OUT = PRIVATE_OUT'),
        ("'--top-module','tb_gpu_transluc',", "'--top-module','tb_gpu_transluc',*PARAMS,"),
        # Model the working-tree GPU instead of the frozen 2026-09-22 copy.
        ("    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()",
         "    shutil.copy2(ROOT/'src/fpga/common/gpu_core.v', frozen/'common/gpu_core.v')\n"
         "    top = frozen/'tb_gpu_transluc.v'; s = top.read_text()"),
    ]:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    ns = dict(__file__=str(BASE/'build.py'), __name__='private_build',
              PRIVATE_OUT=out, PARAMS=VARIANTS[a.variant])
    exec(compile(source, str(BASE/'build.py'), 'exec'), ns)
    ns['main']()

if __name__ == '__main__': main()
